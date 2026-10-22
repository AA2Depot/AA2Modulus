"""Reasons an expression, action or event is recovered as raw syntax."""

from __future__ import annotations

from ...core.source_names import is_source_name
from ...model.control_flow import (
    ACTION_FORLOOP,
    ACTION_SETVAR,
)
from ...model.records import Event, Expression, GuiAction, NamedConstantRef
from ...model.types import (
    EXPR_CONSTANT,
    EXPR_NAMEDCONSTANT,
    EXPR_PAYLOAD_MARKERS,
    EXPR_VAR,
    TypeId,
    ValueType,
)
from .context import (
    FormatContext,
    catalog_name,
)
from .text import type_name


def expression_fallback_reason(
    expression: Expression,
    context: FormatContext,
    expected_type: TypeId | None = None,
) -> str:
    if expression.raw_reference or (
        expression.named_constant is not None and expression.named_constant.raw_reference
    ):
        return "explicit raw provenance"
    if expected_type is not None and expression.return_type != expected_type:
        return (
            f"declaration mismatch: expression type {type_name(expression.return_type)} "
            f"does not match expected type {type_name(expected_type)}"
        )
    reason = _leaf_mismatch_reason(expression, context)
    if reason is not None:
        return reason
    if expression.id == EXPR_NAMEDCONSTANT and expression.named_constant is not None:
        return _named_constant_reason(expression, expression.named_constant, context)
    if expression.id in EXPR_PAYLOAD_MARKERS:
        return "declaration mismatch"
    return _registry_reason(expression, context)


def _leaf_mismatch_reason(expression: Expression, context: FormatContext) -> str | None:
    """The mismatch of a constant or variable whose value disagrees with its declaration."""

    if expression.id == EXPR_CONSTANT and expression.constant is not None:
        if expression.constant.type != expression.return_type:
            return (
                f"declaration mismatch: constant value type {type_name(expression.constant.type)} "
                f"does not match expression type {type_name(expression.return_type)}"
            )
        if expression.constant.type is ValueType.INVALID:
            return f"unknown identity: invalid constant type {type_name(expression.return_type)}"
    if expression.id == EXPR_VAR and expression.variable_name is not None:
        actual = context.variables.get(expression.variable_name)
        if actual is None:
            return f"unresolved variable: {expression.variable_name!r} is not declared"
        if actual != expression.return_type:
            return (
                f"declaration mismatch: variable {expression.variable_name!r} is declared "
                f"{type_name(actual)} but the reference uses {type_name(expression.return_type)}"
            )
    return None


def _named_constant_reason(
    expression: Expression, reference: NamedConstantRef, context: FormatContext
) -> str:
    named = reference.metadata or context.metadata.named_constant(
        reference.value_type, reference.id
    )
    if reference.value_type != expression.return_type:
        return (
            f"declaration mismatch: named constant type {type_name(reference.value_type)} "
            f"does not match expression type {type_name(expression.return_type)}"
        )
    if named is None or named.id != reference.id or named.value_type != reference.value_type:
        return (
            f"unknown identity: named constant {type_name(reference.value_type)} id {reference.id}"
        )
    return (
        f"ambiguous source spelling: named constant "
        f"{type_name(reference.value_type)} id {reference.id} has no unique source name"
    )


def _registry_reason(expression: Expression, context: FormatContext) -> str:
    """Why an expression with registry identity has no readable source form."""

    metadata = expression.metadata or context.metadata.expression(
        expression.return_type, expression.id
    )
    if metadata is None:
        return (
            f"unknown identity: expression {type_name(expression.return_type)} id {expression.id}"
        )
    if metadata.id != expression.id or metadata.return_type != expression.return_type:
        return (
            f"declaration mismatch: expression {type_name(expression.return_type)} "
            f"id {expression.id} does not match its registry declaration"
        )
    if (
        metadata.declared_return_type != expression.return_type
        and not context.catalog.expression_is_readable(expression.return_type, expression.id)
    ):
        return (
            f"declaration mismatch: expression {type_name(expression.return_type)} "
            f"id {expression.id} does not match its registry declaration"
        )
    if tuple(item.return_type for item in expression.parameters) != metadata.parameter_types:
        actual_parameters = (
            ", ".join(type_name(item.return_type) for item in expression.parameters)
            or "no parameters"
        )
        expected_parameters = (
            ", ".join(type_name(item) for item in metadata.parameter_types) or "no parameters"
        )
        return (
            f"incompatible signature: expression {type_name(expression.return_type)} id "
            f"{expression.id} expects ({expected_parameters}) but has ({actual_parameters})"
        )
    return (
        f"ambiguous source spelling: expression {type_name(expression.return_type)} "
        f"id {expression.id} has no unique source name"
    )


def signature_fallback_reason(
    kind: str,
    identifier: int,
    actual: tuple[Expression, ...],
    expected: tuple[TypeId, ...],
) -> str:
    actual_types = tuple(item.return_type for item in actual)
    if len(actual) != len(expected):
        return (
            f"incompatible signature: {kind} id {identifier} expects {len(expected)} "
            f"parameters but has {len(actual)}"
        )
    actual_text = ", ".join(type_name(item) for item in actual_types) or "no parameters"
    expected_text = ", ".join(type_name(item) for item in expected) or "no parameters"
    return (
        f"incompatible signature: {kind} id {identifier} expects ({expected_text}) "
        f"but has ({actual_text})"
    )


def same_signature(
    expressions: tuple[Expression, ...],
    parameter_types: tuple[TypeId, ...],
) -> bool:
    return len(expressions) == len(parameter_types) and all(
        expression.return_type == expected
        for expression, expected in zip(expressions, parameter_types, strict=True)
    )


def action_fallback_reason(action: GuiAction, context: FormatContext) -> str:
    """Why ``action`` is written in raw form, for the fallback diagnostic."""

    call = action.action
    if call.raw_reference:
        return "explicit raw provenance"
    metadata = call.metadata or context.metadata.action(call.id)
    if metadata is None:
        return f"unknown identity: action id {call.id}"
    # Loop and assignment targets take any variable type natively, so their
    # own checks explain a fallback better than the signature comparison.
    if call.id == ACTION_FORLOOP and len(call.parameters) == 3:
        target = call.parameters[0]
        if target.id == EXPR_VAR and target.variable_name is not None:
            actual = context.variables.get(target.variable_name)
            if actual is None:
                return f"unresolved variable: {target.variable_name!r} is not declared"
            if target.return_type != ValueType.INT or actual != ValueType.INT:
                return (
                    f"declaration mismatch: `for` loop target {target.variable_name!r} "
                    f"must be int, declared {type_name(actual)}"
                )
        if any(item.return_type != ValueType.INT for item in call.parameters[1:]):
            return "declaration mismatch: `for` loop bounds must be int"
    if call.id == ACTION_SETVAR and len(call.parameters) == 2:
        target = call.parameters[0]
        if target.id == EXPR_VAR and target.variable_name is not None:
            actual = context.variables.get(target.variable_name)
            if actual is None:
                return f"unresolved variable: {target.variable_name!r} is not declared"
            if target.return_type != actual or call.parameters[1].return_type != target.return_type:
                return (
                    f"declaration mismatch: assignment target {target.variable_name!r} is "
                    f"{type_name(actual)} but the target/value types are "
                    f"{type_name(target.return_type)}/{type_name(call.parameters[1].return_type)}"
                )
    if not same_signature(call.parameters, metadata.parameter_types):
        return signature_fallback_reason(
            "action", call.id, call.parameters, metadata.parameter_types
        )
    name = catalog_name(context, "action", call.id)
    if name is None:
        return f"ambiguous source spelling: action id {call.id} has no source name"
    if not is_source_name(name):
        return f"ambiguous source spelling: action id {call.id} has no source name"
    candidates = context.catalog.action_candidates(name)
    if len(candidates) != 1 or candidates[0].id != call.id:
        return f"ambiguous source spelling: action id {call.id} has no unique source name"
    return f"incompatible signature: action id {call.id} cannot use a readable source form"


def event_fallback_reason(event: Event, context: FormatContext) -> str:
    if event.raw_reference:
        return "explicit raw provenance"
    metadata = event.metadata or context.metadata.event(event.id)
    if metadata is None:
        return f"unknown identity: event id {event.id}"
    if not same_signature(event.parameters, metadata.parameter_types):
        return signature_fallback_reason(
            "event", event.id, event.parameters, metadata.parameter_types
        )
    name = catalog_name(context, "event", event.id)
    if name is None:
        return f"ambiguous source spelling: event id {event.id} has no source name"
    if not is_source_name(name):
        return f"ambiguous source spelling: event id {event.id} has no source name"
    candidates = context.catalog.event_candidates(name)
    if len(candidates) != 1 or candidates[0].id != event.id:
        return f"ambiguous source spelling: event id {event.id} has no unique source name"
    return f"incompatible signature: event id {event.id} cannot use a readable source form"
