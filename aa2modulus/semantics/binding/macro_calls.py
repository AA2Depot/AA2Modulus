"""Macro call statements."""

from __future__ import annotations

from dataclasses import replace

from ...core.diagnostics import Diagnostic
from ...core.locations import RelatedLocation
from ...hir.nodes import (
    BoundExpression,
    BoundStatement,
)
from ...syntax.ast import (
    SourceAction,
)
from ..expansion import (
    substitute_body,
)
from .checks import check_raw_actual
from .expressions import bind_expression
from .reporting import raise_error, record_reference
from .state import BindContext, SourceBindingError


def bind_macro_call(context: BindContext, node: SourceAction) -> tuple[BoundStatement, ...]:
    try:
        return _bind_macro_call_inner(context, node)
    except SourceBindingError as exc:
        template = context.macros.get((node.name or "").casefold())
        if template is None or template.definition.source_span is None:
            raise
        note = RelatedLocation(template.definition.source_span, "macro defined here")
        diagnostics: list[Diagnostic] = []
        for diagnostic in exc.diagnostics:
            notes = diagnostic.related
            if note not in notes:
                notes = (*notes, note, *template.definition.source_span.related)
            diagnostics.append(replace(diagnostic, related=notes))
        raise SourceBindingError(diagnostics[0], tuple(diagnostics)) from exc


def _bind_macro_call_inner(context: BindContext, node: SourceAction) -> tuple[BoundStatement, ...]:
    assert node.name is not None
    template = context.macros[node.name.casefold()]
    definition = template.definition
    record_reference(context, node.name, node, declaration=definition)
    parameters = definition.parameters
    if node.has_block or node.children:
        raise_error(context, node, "MACRO_CALL_BLOCK", "macro calls require a semicolon")
    if len(node.arguments) != len(parameters):
        raise_error(
            context,
            node,
            "MACRO_ARITY",
            f"macro {definition.name!r} requires {len(parameters)} arguments",
        )
    arguments = node.arguments
    actuals: dict[str, BoundExpression] = {}
    errors: list[Diagnostic] = []
    for parameter, argument in zip(parameters, arguments, strict=False):
        try:
            actuals[parameter.name] = bind_expression(context, argument, parameter.type)
            check_raw_actual(
                context,
                argument,
                actuals[parameter.name],
                ("macros", definition.name, "arguments", parameter.name),
                tuple(
                    RelatedLocation(span, message)
                    for span, message in (
                        (parameter.source_span, f"formal {parameter.name!r} declared here"),
                        (node.source_span, f"macro {definition.name!r} invoked here"),
                        (definition.source_span, "macro defined here"),
                    )
                    if span is not None
                ),
            )
        except SourceBindingError as exc:
            for diagnostic in exc.diagnostics:
                notes = list(diagnostic.related)
                if parameter.source_span is not None:
                    notes.append(
                        RelatedLocation(
                            parameter.source_span, f"formal {parameter.name!r} declared here"
                        )
                    )
                if node.source_span is not None:
                    notes.append(
                        RelatedLocation(node.source_span, f"macro {definition.name!r} invoked here")
                    )
                errors.append(replace(diagnostic, related=tuple(notes)))
    if errors:
        raise SourceBindingError(errors[0], tuple(errors))
    assert context.expansion_budget is not None
    return substitute_body(
        template,
        actuals,
        node.source_span,
        context.expansion_budget,
        depth=context.depth,
        nesting=context.nesting - 1,
    )
