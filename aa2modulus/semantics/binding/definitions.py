"""Macro and trigger-template preparation and instantiation."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ...context.operation import SourceContext
from ...core.diagnostics import Diagnostic
from ...core.locations import RelatedLocation, with_related
from ...core.source_names import is_source_name
from ...hir.nodes import (
    BoundExpression,
    BoundTrigger,
)
from ...hir.symbols import ResolvedConstant
from ...language.types import (
    CARD,
    SourceType,
    wire_type,
)
from ...syntax.ast import (
    SourceMacro,
    SourceParameter,
    SourceRawExpression,
    SourceRawVariable,
    SourceSlotBinding,
    SourceTriggerImport,
    SourceTriggerTemplate,
)
from ...syntax.walk import walk_ast
from ..expansion import (
    MacroTemplate,
    substitute_hir,
)
from .checks import check_raw_actual, validate_macro_body, validate_template
from .declarations import check_constant_collision, check_protected_declaration
from .expressions import bind_expression
from .reporting import bind_or_record, raise_error, record_reference
from .state import BindContext, Poisoned, SourceBindingError
from .statements import bind_children
from .triggers import bind_trigger
from .values import SCALAR_DEFAULTS, check_type


@dataclass(frozen=True, slots=True)
class TriggerTemplate:
    definition: SourceTriggerTemplate
    trigger: BoundTrigger


def prepare_templates(
    context: BindContext,
    definitions: tuple[SourceTriggerTemplate, ...],
    operation: SourceContext,
    constants: dict[str, ResolvedConstant],
    hidden: dict[str, ResolvedConstant],
) -> tuple[dict[str, TriggerTemplate], tuple[Diagnostic, ...]]:
    """Bind and validate each template once; a failing one is poisoned, not registered."""

    collector = context.collector
    assert collector is not None
    templates: dict[str, TriggerTemplate] = {}
    seen: dict[str, SourceTriggerTemplate] = {}
    diagnostics: list[Diagnostic] = []
    for definition in definitions:
        if definition.name in seen:
            previous = seen[definition.name].source_span
            notes = (
                ()
                if previous is None
                else (RelatedLocation(previous, "previous template defined here"),)
            )
            raise_error(
                context,
                replace(definition, source_span=with_related(definition.source_span, notes)),
                "DUPLICATE_TEMPLATE",
                f"duplicate template {definition.name!r}",
            )
        seen[definition.name] = definition
        mark = collector.mark()
        prepared = bind_or_record(
            context, _prepare_template, context, definition, operation, constants, hidden
        )
        if prepared is None or collector.failed_since(mark):
            collector.poisoned_templates.add(definition.name)
            continue
        template, warnings = prepared
        diagnostics.extend(warnings)
        templates[definition.name] = template
    return templates, tuple(diagnostics)


def _prepare_template(
    context: BindContext,
    definition: SourceTriggerTemplate,
    operation: SourceContext,
    constants: dict[str, ResolvedConstant],
    hidden: dict[str, ResolvedConstant],
) -> tuple[TriggerTemplate, tuple[Diagnostic, ...]]:
    """Bind a template body once in a scope of its slots; ``Poisoned`` if the body fails."""

    if not definition.name:
        raise_error(context, definition, "TEMPLATE_NAME", "template names cannot be empty")
    slots: dict[str, SourceType] = {}
    for item in definition.slots:
        if not is_source_name(item.name, allow_qualified=False):
            raise_error(context, item, "TEMPLATE_SLOT_NAME", f"invalid slot name {item.name!r}")
        if item.name in slots:
            raise_error(context, item, "DUPLICATE_TEMPLATE_SLOT", f"duplicate slot {item.name!r}")
        check_protected_declaration(context, item, serialized=False)
        check_constant_collision(context, item.name, item, "slot", constants)
        if item.type is not CARD and (
            isinstance(item.type, bool) or item.type not in SCALAR_DEFAULTS
        ):
            raise_error(
                context,
                item,
                "TEMPLATE_SLOT_TYPE",
                "slots require card, int, bool, float, or string",
            )
        slots[item.name] = item.type
    for local in definition.trigger.locals:
        if local.name in slots:
            raise_error(
                context,
                local,
                "TEMPLATE_SLOT_LOCAL_COLLISION",
                f"local {local.name!r} collides with a slot",
            )
    isolated = context.derive(
        locals_=dict(slots),
        local_declarations={item.name: item for item in definition.slots},
        template_definition=definition,
        constants=constants,
        hidden_constants=hidden,
    )
    collector = context.collector
    assert collector is not None
    mark = collector.mark()
    trigger = bind_trigger(isolated, definition.trigger)
    if collector.failed_since(mark):
        # A partially bound body would only add spurious validation errors.
        raise Poisoned
    assert context.expansion_budget is not None
    context.expansion_budget.preflight(trigger, {}, definition.source_span, kind="template")
    warnings = validate_template(isolated, definition, trigger, operation, context.allows)
    context.references.extend(isolated.references)
    return TriggerTemplate(definition, trigger), warnings


def instantiate_trigger(
    context: BindContext,
    node: SourceTriggerImport,
    templates: dict[str, TriggerTemplate],
) -> BoundTrigger:
    """Expand ``node`` into a copy of its template's bound trigger with every slot bound.

    Template locals are renamed apart from the caller's names, and errors gain a
    note at the template definition.
    """

    template = templates.get(node.template)
    if template is None:
        raise_error(context, node, "UNKNOWN_TEMPLATE", f"unknown template {node.template!r}")
    definition = template.definition
    note = (
        ()
        if definition.source_span is None
        else (
            RelatedLocation(definition.source_span, "template defined here"),
            *definition.source_span.related,
        )
    )
    try:
        parameters = {item.name: item for item in definition.slots}
        actuals: dict[str, BoundExpression] = {}
        for binding in node.slots:
            if binding.name in actuals:
                raise_error(
                    context,
                    binding,
                    "DUPLICATE_SLOT_BINDING",
                    f"duplicate binding for {binding.name!r}",
                )
            parameter = parameters.get(binding.name)
            if parameter is None:
                raise_error(context, binding, "UNKNOWN_SLOT", f"unknown slot {binding.name!r}")
            record_reference(
                context, binding.name, binding, declaration=parameter, value_type=parameter.type
            )
            actuals[binding.name] = _bind_slot(context, binding, parameter, node, definition)
        missing = tuple(name for name in parameters if name not in actuals)
        if missing:
            raise_error(
                context, node, "MISSING_SLOT", f"missing required slots: {', '.join(missing)}"
            )
        name = definition.name if node.name is None else node.name
        if not name:
            raise_error(
                context, node, "TEMPLATE_TRIGGER_NAME", "instantiated trigger names cannot be empty"
            )
        assert context.expansion_budget is not None
        trigger = substitute_hir(
            template.trigger,
            actuals,
            node.source_span,
            context.expansion_budget,
            depth=2,
            nesting=0,
            kind="template",
            name=definition.name,
            renames=_local_renames(context, template),
        )
        record_reference(
            context,
            node.template,
            node,
            declaration=definition,
        )
        return replace(trigger, name=name)
    except SourceBindingError as exc:
        raise SourceBindingError(
            replace(exc.diagnostic, related=(*exc.diagnostic.related, *note))
        ) from exc


def _bind_slot(
    context: BindContext,
    binding: SourceSlotBinding,
    parameter: SourceParameter,
    node: SourceTriggerImport,
    definition: SourceTriggerTemplate,
) -> BoundExpression:
    """Bind one slot actual; its errors note the slot and the template invocation."""

    try:
        for raw in walk_ast(binding.value):
            if isinstance(raw, SourceRawExpression) and isinstance(raw.payload, SourceRawVariable):
                actual_type = context.globals.get(raw.payload.name)
                if actual_type is None:
                    raise_error(
                        context,
                        raw,
                        "TEMPLATE_CAPTURE",
                        "raw slot actual variable references require a declared module global",
                    )
                check_type(context, raw.return_type, wire_type(actual_type), raw)
        actual = bind_expression(context, binding.value, parameter.type)
        check_raw_actual(
            context,
            binding.value,
            actual,
            ("templates", definition.name, "slots", binding.name),
            tuple(
                RelatedLocation(span, message)
                for span, message in (
                    (parameter.source_span, f"slot {parameter.name!r} declared here"),
                    (node.source_span, f"template {definition.name!r} invoked here"),
                    (definition.source_span, "template defined here"),
                )
                if span is not None
            ),
        )
    except SourceBindingError as exc:
        parameter_note = (
            ()
            if parameter.source_span is None
            else (RelatedLocation(parameter.source_span, f"slot {parameter.name!r} declared here"),)
        )
        invocation_note = (
            ()
            if node.source_span is None
            else (RelatedLocation(node.source_span, f"template {definition.name!r} invoked here"),)
        )
        raise SourceBindingError(
            replace(
                exc.diagnostic,
                related=(*exc.diagnostic.related, *parameter_note, *invocation_note),
            )
        ) from exc
    return actual


def _local_renames(context: BindContext, template: TriggerTemplate) -> dict[str, str]:
    """Fresh names for template locals that a module global of the same name would shadow."""

    occupied = set(context.globals) | {item.name for item in template.trigger.locals}
    renames: dict[str, str] = {}
    candidate = 0
    for item in template.trigger.locals:
        if item.name in context.globals:
            while (fresh := f"_aa2m_local_{candidate}") in occupied:
                candidate += 1
            occupied.add(fresh)
            renames[item.name] = fresh
            candidate += 1
    return renames


def prepare_macro(
    context: BindContext,
    definition: SourceMacro,
    operation: SourceContext,
    constants: dict[str, ResolvedConstant],
    hidden: dict[str, ResolvedConstant],
) -> tuple[MacroTemplate, tuple[Diagnostic, ...]]:
    """Bind and validate one macro definition; a body with collected errors is poisoned."""

    formal_context = context.derive(
        locals_={item.name: item.type for item in definition.parameters},
        local_declarations={item.name: item for item in definition.parameters},
        macro_definition=definition,
        depth=0,
        constants=constants,
        hidden_constants=hidden,
    )
    for parameter in definition.parameters:
        check_protected_declaration(formal_context, parameter, serialized=False)
        check_constant_collision(formal_context, parameter.name, parameter, "macro formal")
    collector = context.collector
    assert collector is not None
    mark = collector.mark()
    body = bind_children(formal_context, definition.body)
    if collector.failed_since(mark):
        raise Poisoned
    assert context.expansion_budget is not None
    context.expansion_budget.preflight(body, {}, definition.source_span)
    warnings = validate_macro_body(
        definition, body, operation, context.binding_budget, context.allows
    )
    context.references.extend(formal_context.references)
    return MacroTemplate(definition, body), warnings
