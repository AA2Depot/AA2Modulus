"""Authoring view and visible declarations at a cursor."""

from __future__ import annotations

from ...context.operation import SourceContext
from ...core.locations import SourceSpan, line_column
from ...model.values import Value
from ...pipeline.analysis import SourceAnalysis
from ...pipeline.authoring import SourceAuthoring, analyze_authoring
from ...semantics.binding.constants import authoring_constants
from ...syntax.ast import (
    SourceConstant,
    SourceGlobal,
    SourceLocal,
    SourceParameter,
    SourceTrigger,
    SourceUnit,
)


def authoring_view(
    source: str,
    context: SourceContext,
    analysis: SourceAnalysis | None,
    authoring: SourceAuthoring | None,
) -> SourceAuthoring:
    if authoring is not None and authoring.source == source:
        return authoring
    if analysis is not None and analysis.source != source:
        return SourceAuthoring(source=source)
    return analyze_authoring(
        source,
        context,
        analysis=analysis,
        source_kind="library" if context.filename.endswith(".aa2mi") else "module",
    )


def visible_declarations(
    unit: SourceUnit | None, source: str, offset: int, context: SourceContext
) -> tuple[SourceGlobal | SourceLocal | SourceParameter | SourceConstant, ...]:
    """Declarations in scope at ``offset``: the enclosing definition's names, then constants."""

    line, column = line_column(source, offset)

    def contains(span: SourceSpan | None) -> bool:
        return (
            span is not None
            and span.filename == context.filename
            and (span.start_line, span.start_column) <= (line, column)
            and (
                span.end_line is None
                or span.end_column is None
                or (line, column) <= (span.end_line, span.end_column + 1)
            )
        )

    if unit is None:
        return ()
    # Top-level constants are visible everywhere; module constants only in the module.
    top_constants = tuple(unit.constants)
    macro = next((item for item in unit.macros if contains(item.source_span)), None)
    if macro is not None:
        return (*macro.parameters, *top_constants)
    template = next(
        (
            item
            for item in unit.templates
            if contains(item.source_span) or contains(item.trigger.source_span)
        ),
        None,
    )
    if template is not None:
        template_declarations: dict[str, SourceParameter | SourceLocal] = {}
        for slot in template.slots:
            template_declarations.setdefault(slot.name, slot)
        for local in template.trigger.locals:
            template_declarations.setdefault(local.name, local)
        return (*template_declarations.values(), *top_constants)
    if unit.module is not None:
        module_declarations: dict[str, SourceGlobal | SourceLocal | SourceConstant] = {}
        for global_ in unit.module.globals:
            module_declarations.setdefault(global_.name, global_)
        for trigger in unit.module.triggers:
            if isinstance(trigger, SourceTrigger) and contains(trigger.source_span):
                for local in trigger.locals:
                    module_declarations.setdefault(local.name, local)
        for constant in (*top_constants, *unit.module.constants):
            module_declarations.setdefault(constant.name, constant)
        return tuple(module_declarations.values())
    return top_constants


def constant_values(unit: SourceUnit | None, context: SourceContext) -> dict[int, Value | None]:
    """Resolved constant values keyed by declaration identity; empty on failure."""

    if unit is None:
        return {}
    try:
        top, module = authoring_constants(unit, context)
    except Exception:  # editor views must never fail a request
        return {}
    return {id(item.declaration): item.value for item in (*top, *module)}
