"""Definition checks: raw actuals and macro bodies against SIR validation."""

from __future__ import annotations

from collections import ChainMap
from dataclasses import replace

from ...context.operation import SourceContext
from ...core.diagnostics import Diagnostic, ValidationResult
from ...core.locations import RelatedLocation
from ...hir.limits import BindingBudget
from ...hir.nodes import (
    BoundExpression,
    BoundLiteral,
    BoundLocal,
    BoundModule,
    BoundStatement,
    BoundTrigger,
)
from ...language.types import (
    wire_type,
)
from ...lowering.expressions import lower_expression
from ...lowering.module import lower_bound_module
from ...syntax.ast import (
    SourceAllow,
    SourceExpression,
    SourceLiteral,
    SourceMacro,
    SourceRawExpression,
    SourceTriggerTemplate,
)
from ...syntax.walk import walk_ast
from ...validation.validator.module import validate_expression_in_scope, validate_module
from ..allows import acknowledge
from .state import BindContext, SourceBindingError
from .values import SCALAR_DEFAULTS, literal_value


def check_raw_actual(
    context: BindContext,
    syntax: SourceExpression,
    actual: BoundExpression,
    path: tuple[str | int, ...],
    notes: tuple[RelatedLocation, ...],
) -> None:
    """Retain strict checks for raw arguments even when expansion drops them."""

    if not any(isinstance(node, SourceRawExpression) for node in walk_ast(syntax)):
        return
    result = validate_expression_in_scope(
        lower_expression(actual),
        context.metadata,
        filename=context.filename,
        variables=ChainMap(
            {name: wire_type(kind) for name, kind in context.globals.items()},
            {name: wire_type(kind) for name, kind in context.locals.items()},
        ),
        catalog=context.catalog,
    )
    context.input_diagnostics.extend(
        replace(item, path=(*path, *item.path), related=(*item.related, *notes))
        for item in result.diagnostics
    )


def validate_macro_body(
    definition: SourceMacro,
    body: tuple[BoundStatement, ...],
    operation: SourceContext,
    binding_budget: BindingBudget,
    allows: tuple[SourceAllow, ...],
) -> tuple[Diagnostic, ...]:
    """Use ordinary SIR validation for every definition, without emitting it."""

    formal_context = BindContext(
        operation.metadata,
        operation.source_policy,
        operation.filename,
        {},
        {},
        catalog=operation.catalog,
        binding_budget=binding_budget,
    )
    locals_ = tuple(
        BoundLocal(
            item.name,
            item.type,
            BoundLiteral(
                literal_value(formal_context, SourceLiteral(SCALAR_DEFAULTS[wire_type(item.type)]))
            ),
            source_span=item.source_span,
        )
        for item in definition.parameters
    )
    prepared = BoundModule(
        definition.name, triggers=(BoundTrigger(definition.name, locals=locals_, statements=body),)
    )
    result = acknowledged(
        validate_module(
            lower_bound_module(prepared, context=operation),
            metadata=operation.metadata,
            filename=operation.filename,
            catalog=operation.catalog,
        ),
        allows,
        operation,
    )
    if result.errors:
        raise SourceBindingError(result.errors[0], result.errors)
    return tuple(
        replace(item, path=("macros", definition.name))
        for item in result.warnings
        if item.code != "REVIEWED_VALUE_CONTEXT_UNKNOWN"
    )


def validate_template(
    context: BindContext,
    definition: SourceTriggerTemplate,
    trigger: BoundTrigger,
    operation: SourceContext,
    allows: tuple[SourceAllow, ...],
) -> tuple[Diagnostic, ...]:
    """Validate a bound template as a stub trigger whose slots are defaulted locals.

    ``context`` is the template's own scope, used to type the slot defaults.
    """

    formal_locals = tuple(
        BoundLocal(
            item.name,
            item.type,
            BoundLiteral(
                literal_value(context, SourceLiteral(SCALAR_DEFAULTS[wire_type(item.type)]))
            ),
            source_span=item.source_span,
        )
        for item in definition.slots
    )
    stub = BoundModule(
        "<template>", triggers=(replace(trigger, locals=(*formal_locals, *trigger.locals)),)
    )
    result = acknowledged(
        validate_module(
            lower_bound_module(stub, context=operation),
            metadata=operation.metadata,
            filename=operation.filename,
            catalog=operation.catalog,
        ),
        allows,
        operation,
    )
    if result.errors:
        raise SourceBindingError(result.errors[0], result.errors)
    return tuple(replace(item, path=("templates", definition.name)) for item in result.warnings)


def acknowledged(
    result: ValidationResult, allows: tuple[SourceAllow, ...], operation: SourceContext
) -> ValidationResult:
    """A definition's validation with `@allow`-covered hazard errors as warnings."""

    if not allows:
        return result
    diagnostics, _used = acknowledge(
        result.diagnostics, allows, operation.source_policy.acknowledgeable_codes
    )
    return ValidationResult(diagnostics)
