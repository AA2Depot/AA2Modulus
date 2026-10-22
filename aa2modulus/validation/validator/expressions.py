"""Expression checks, one function per expression kind."""

from __future__ import annotations

from ...model.display import type_name
from ...model.native import ExpressionMetadata
from ...model.records import Expression, NamedConstantRef
from ...model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, ValueType
from .event_values import validate_reviewed_expression
from .state import ValidatorState
from .value_types import check_expected_type, known_type, validate_value


def validate_expression(
    state: ValidatorState,
    expression: Expression,
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
    *,
    allow_assignment_target: bool = False,
) -> None:
    if state.resolving_only:
        _resolve_variables(state, expression, trigger_path, path)
        return
    metadata = _check_target(state, expression, path)
    if expression.id == EXPR_CONSTANT:
        if expression.constant is not None:
            validate_value(state, expression.constant, (*path, "constant"), expression.return_type)
        return
    if expression.id == EXPR_VAR:
        _validate_variable(state, expression, path, allow_assignment_target)
        return
    if expression.id == EXPR_NAMEDCONSTANT:
        _validate_named_constant(state, expression, path)
        return
    _validate_call(state, expression, metadata, trigger_path, path)


def _resolve_variables(
    state: ValidatorState,
    expression: Expression,
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
) -> None:
    """The native pre-pass: only undefined variables, in every nested expression."""

    if expression.id == EXPR_VAR and state.scope.lookup(expression.variable_name or "") is None:
        help, fixes = state.undeclared_help(expression.variable_name or "", expression.return_type)
        state.reporter.add(
            expression,
            path,
            "UNDEFINED_VARIABLE",
            f"undefined variable {expression.variable_name!r}",
            field_path=("variable_name",),
            help=help,
            fixes=fixes,
        )
    for index, child in enumerate(expression.parameters):
        validate_expression(state, child, trigger_path, (*path, "parameters", index))


def _check_target(
    state: ValidatorState, expression: Expression, path: tuple[str | int, ...]
) -> ExpressionMetadata | None:
    """Return type, registry entry, native defects and reviewed native claims."""

    if not known_type(expression.return_type):
        state.reporter.add(
            expression,
            path,
            "INVALID_EXPRESSION_RETURN_TYPE",
            f"expression has invalid return type {type_name(expression.return_type)}",
            field_path=("return_type",),
        )

    expression_metadata = state.metadata.expression(expression.return_type, expression.id)
    if expression_metadata is None:
        state.reporter.add(
            expression,
            path,
            "UNKNOWN_EXPRESSION",
            f"unknown expression id {expression.id} in return-type scope "
            f"{type_name(expression.return_type)}",
            field_path=("id",),
        )
    elif expression_metadata.declared_return_type != expression_metadata.return_type:
        declared_return_type = expression_metadata.declared_return_type
        assert declared_return_type is not None
        state.reporter.add(
            expression,
            path,
            "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH",
            f"{state.labels.expression(expression)} is resolved in "
            f"{type_name(expression_metadata.return_type)} scope but declares "
            f"{type_name(declared_return_type)}",
            severity=state.authoring_severity,
            field_path=("return_type",),
            notes=state.labels.native_note("expression", expression.id, expression.return_type),
        )

    defect = (
        state.catalog.expression_defect(expression.return_type, expression.id)
        if state.catalog is not None and expression_metadata is not None
        else None
    )
    if defect is not None:
        state.reporter.add(
            expression,
            path,
            "NATIVE_DEFECTIVE_EXPRESSION",
            f"{state.labels.expression(expression)} cannot work in AAUnlimited: {defect}",
            severity=state.authoring_severity,
            field_path=("id",),
        )

    validate_reviewed_expression(state, expression, path)
    return expression_metadata


def _validate_variable(
    state: ValidatorState,
    expression: Expression,
    path: tuple[str | int, ...],
    allow_assignment_target: bool,
) -> None:
    binding = state.scope.lookup(expression.variable_name or "")
    if binding is None and not state.native:
        help, fixes = state.undeclared_help(expression.variable_name or "", expression.return_type)
        state.reporter.add(
            expression,
            path,
            "UNDEFINED_VARIABLE",
            f"undefined variable {expression.variable_name!r}",
            field_path=("variable_name",),
            help=help,
            fixes=fixes,
        )
    elif (
        binding is not None
        and expression.return_type != binding.type
        and not (allow_assignment_target and expression.return_type is ValueType.INVALID)
    ):
        state.reporter.add(
            expression,
            path,
            "VARIABLE_TYPE_MISMATCH",
            f"variable {binding.name!r} has type "
            f"{type_name(binding.type)}, but expression returns "
            f"{type_name(expression.return_type)}",
            field_path=("return_type",),
            severity=state.authoring_severity,
        )


def _validate_named_constant(
    state: ValidatorState, expression: Expression, path: tuple[str | int, ...]
) -> None:
    reference = expression.named_constant
    if not isinstance(reference, NamedConstantRef):
        return
    if reference.value_type != expression.return_type:
        state.reporter.add(
            reference,
            (*path, "named_constant_id"),
            "NAMED_CONSTANT_TYPE_MISMATCH",
            f"named constant scope {type_name(reference.value_type)} "
            f"does not match expression return type "
            f"{type_name(expression.return_type)}",
        )
    constant_metadata = state.metadata.named_constant(reference.value_type, reference.id)
    if constant_metadata is None:
        state.reporter.add(
            reference,
            (*path, "named_constant_id"),
            "UNKNOWN_NAMED_CONSTANT",
            f"unknown named constant id {reference.id} in type scope "
            f"{type_name(reference.value_type)}",
        )
    elif constant_metadata.value_type != expression.return_type:
        state.reporter.add(
            reference,
            (*path, "named_constant_id"),
            "NAMED_CONSTANT_TYPE_MISMATCH",
            f"named constant {constant_metadata.name!r} has type "
            f"{type_name(constant_metadata.value_type)}, but expression "
            f"returns {type_name(expression.return_type)}",
        )


def _validate_call(
    state: ValidatorState,
    expression: Expression,
    metadata: ExpressionMetadata | None,
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
) -> None:
    if metadata is None:
        for index, child in enumerate(expression.parameters):
            validate_expression(state, child, trigger_path, (*path, "parameters", index))
        return
    expected_parameters = metadata.parameter_types
    label = state.labels.expression(expression)
    native_note = state.labels.native_note("expression", expression.id, expression.return_type)
    if len(expression.parameters) != len(expected_parameters):
        state.reporter.add(
            expression,
            path,
            "EXPRESSION_ARITY",
            f"{label} expects {len(expected_parameters)} parameters, "
            f"but found {len(expression.parameters)}",
            field_path=("parameters",),
            notes=native_note,
        )
    for index, child in enumerate(expression.parameters):
        if index < len(expected_parameters):
            check_expected_type(
                state,
                child,
                expected_parameters[index],
                (*path, "parameters", index),
                label,
                index,
                "EXPRESSION_PARAMETER_TYPE",
                native_note,
            )
        validate_expression(state, child, trigger_path, (*path, "parameters", index))
