"""Bind a Source AST module or unit into a bound module."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ...context.limits import SourceLimits
from ...context.operation import SourceContext
from ...context.resolver import SourceResolver
from ...core.diagnostics import Diagnostic
from ...hir.limits import BindingBudget
from ...hir.nodes import (
    BoundGlobal,
    BoundLiteral,
    BoundModule,
    BoundTrigger,
)
from ...hir.symbols import ResolvedConstant
from ...language.types import (
    wire_type,
)
from ...metadata.snapshot import MetadataSnapshot
from ...syntax.ast import (
    SourceConstant,
    SourceGlobal,
    SourceLiteral,
    SourceMacro,
    SourceModule,
    SourceTrigger,
    SourceTriggerImport,
    SourceUnit,
)
from ...syntax.imports import resolve_source_imports
from ...syntax.limits import check_source_ast
from ...validation.validator.declarations import declaration_anchor
from ..expansion import (
    ExpansionBudget,
    MacroTemplate,
    definition_order,
)
from .constants import global_value, resolve_constants
from .declarations import check_constant_collision, check_protected_declaration
from .definitions import TriggerTemplate, instantiate_trigger, prepare_macro, prepare_templates
from .reporting import bind_or_record, node_span, raise_error
from .state import BindContext, ErrorCollector, ErrorLimit, SourceBindingError
from .triggers import bind_trigger
from .values import check_type


def bind_source_ast(
    source: SourceModule | SourceUnit,
    *,
    context: SourceContext | None = None,
    filename: str | None = None,
    metadata: MetadataSnapshot | None = None,
    source_limits: SourceLimits | None = None,
    import_base: str | Path | None = None,
    source_resolver: SourceResolver | None = None,
) -> BoundModule:
    """Resolve a unified Source AST into Bound HIR."""

    operation = SourceContext.resolve(
        context,
        filename=filename,
        metadata=metadata,
        source_limits=source_limits,
        import_base=import_base,
        source_resolver=source_resolver,
    )
    check_source_ast(source, filename=operation.filename, limits=operation.source_limits)
    top_constants: tuple[SourceConstant, ...] = ()
    if isinstance(source, SourceUnit):
        source = resolve_source_imports(source, operation)
        top_constants = source.constants
        if source.module is None:
            raise ValueError(
                "binding requires a module unit; use validate_source with source_kind='library'"
            )
    collector = ErrorCollector(operation.source_limits.max_binding_errors)
    stopped: tuple[Diagnostic, ...] = ()
    try:
        bound = _bind_module(source, top_constants, operation, collector)
    except SourceBindingError as exc:
        stopped = exc.diagnostics
    except ErrorLimit:
        pass
    errors = _source_order((*collector.errors, *stopped))
    if len(errors) > collector.limit:
        overflow = errors[collector.limit]
        errors = (
            *errors[: collector.limit],
            replace(
                overflow,
                code="SOURCE_BINDING_ERROR_LIMIT",
                message=f"binding stopped after {collector.limit} errors",
                help=None,
                notes=(),
                fixes=(),
                related=(),
            ),
        )
    if errors:
        raise SourceBindingError(errors[0], errors)
    return bound


def _source_order(diagnostics: tuple[Diagnostic, ...]) -> tuple[Diagnostic, ...]:
    """Order by position within each file, files in order of their first error."""

    unique = tuple(dict.fromkeys(diagnostics))
    files = {item.filename: index for index, item in reversed(tuple(enumerate(unique)))}
    return tuple(sorted(unique, key=lambda item: (files[item.filename], item.line, item.column)))


def _bind_global(context: BindContext, node: SourceGlobal) -> BoundGlobal:
    check_protected_declaration(context, node, serialized=True)
    check_constant_collision(context, node.name, node, "global")
    default = global_value(context, node.default or SourceLiteral(None))
    current = global_value(context, node.current or node.default or SourceLiteral(None))
    # Global values are literals or constants, so a card global takes any int.
    check_type(context, default.type, wire_type(node.type), node)
    check_type(context, current.type, wire_type(node.type), node)
    return BoundGlobal(
        name=node.name,
        type=node.type,
        default=BoundLiteral(default),
        current=BoundLiteral(current),
        initialized=bool(node.initialized),
        source_span=node_span(node),
    )


def _bind_module(
    source: SourceModule | SourceUnit,
    top_constants: tuple[SourceConstant, ...],
    operation: SourceContext,
    collector: ErrorCollector,
) -> BoundModule:
    """Bind every item, collecting independent errors in ``collector``.

    Each constant, macro, template, global, trigger and statement is an error
    boundary. A failed declaration keeps its name and type in scope; a failed
    macro or template is poisoned, so its uses report nothing further.
    """

    binding_context = BindContext(
        metadata=operation.metadata,
        source_policy=operation.source_policy,
        catalog=operation.catalog,
        filename=operation.filename,
        globals={},
        locals={},
        expansion_budget=ExpansionBudget(operation.source_limits, operation.filename),
        binding_budget=BindingBudget(operation.source_limits, operation.filename),
        collector=collector,
        allows=source.allows if isinstance(source, SourceUnit) else (),
    )
    definition_diagnostics: list[Diagnostic] = []
    templates: dict[str, TriggerTemplate] = {}
    module_constants = source.constants if isinstance(source, SourceModule) else ()
    if isinstance(source, SourceUnit):
        assert source.module is not None
        module_constants = source.module.constants
    resolved_constants = resolve_constants(binding_context, top_constants, module_constants)
    top_table = {name: item for name, item in resolved_constants.items() if item.top_level}
    binding_context.constants = resolved_constants
    module_only = {name: item for name, item in resolved_constants.items() if not item.top_level}
    if isinstance(source, SourceUnit):
        ordered = definition_order(
            source.macros,
            operation,
            lambda node, code, message: raise_error(binding_context, node, code, message),
        )
        definition_diagnostics.extend(
            _prepare_macros(binding_context, ordered, operation, top_table, module_only)
        )
        templates, template_diagnostics = prepare_templates(
            binding_context, source.templates, operation, top_table, module_only
        )
        definition_diagnostics.extend(template_diagnostics)
        assert source.module is not None
        source = source.module
    binding_context.declaration_anchor = declaration_anchor(
        source.source_span,
        (item.source_span for item in source.globals),
        (item.source_span for item in source.triggers),
    )
    globals_ = _bind_globals(binding_context, source, operation)
    triggers = _bind_triggers(binding_context, source, templates, collector)
    return BoundModule(
        name=source.name,
        description=source.description,
        dependencies=source.dependencies,
        globals=tuple(globals_),
        triggers=tuple(triggers),
        source_span=node_span(source),
        diagnostics=(*definition_diagnostics, *binding_context.input_diagnostics),
        references=tuple(binding_context.references),
    )


def _prepare_macros(
    binding_context: BindContext,
    ordered: tuple[SourceMacro, ...],
    operation: SourceContext,
    top_table: dict[str, ResolvedConstant],
    module_only: dict[str, ResolvedConstant],
) -> list[Diagnostic]:
    """Prepare macros in dependency order; a failed macro is registered as poisoned."""

    collector = binding_context.collector
    assert collector is not None
    diagnostics: list[Diagnostic] = []
    for definition in ordered:
        key = definition.name.casefold()
        mark = collector.mark()
        prepared = bind_or_record(
            binding_context,
            prepare_macro,
            binding_context,
            definition,
            operation,
            top_table,
            module_only,
        )
        if prepared is None or collector.failed_since(mark):
            # Registered so calls still route to the macro; they report nothing.
            collector.poisoned_macros.add(key)
            binding_context.macros[key] = MacroTemplate(definition, ())
            continue
        template, warnings = prepared
        diagnostics.extend(warnings)
        binding_context.macros[key] = template
    return diagnostics


def _bind_globals(
    binding_context: BindContext, source: SourceModule, operation: SourceContext
) -> list[BoundGlobal]:
    """Bind globals and register them as the module's variable scope."""

    globals_: list[BoundGlobal] = []
    for node in source.globals:
        bound_global = bind_or_record(binding_context, _bind_global, binding_context, node)
        if bound_global is not None:
            globals_.append(bound_global)
        binding_context.globals.setdefault(node.name, node.type)
        binding_context.global_declarations.setdefault(node.name, node)
    return globals_


def _bind_triggers(
    binding_context: BindContext,
    source: SourceModule,
    templates: dict[str, TriggerTemplate],
    collector: ErrorCollector,
) -> list[BoundTrigger]:
    """Bind triggers and instantiate imported templates, each with fresh locals."""

    triggers: list[BoundTrigger] = []
    occupied_triggers = {item.name for item in source.triggers if isinstance(item, SourceTrigger)}
    for trigger in source.triggers:
        binding_context.locals = {}
        binding_context.local_declarations = {}
        bound_trigger: BoundTrigger | None
        if isinstance(trigger, SourceTriggerImport):
            name = trigger.template if trigger.name is None else trigger.name
            if name in occupied_triggers:
                raise_error(
                    binding_context,
                    trigger,
                    "TEMPLATE_TRIGGER_NAME_COLLISION",
                    f"trigger name {name!r} is already in use",
                )
            if trigger.template in collector.poisoned_templates:
                collector.suppressed += 1
                continue
            bound_trigger = bind_or_record(
                binding_context, instantiate_trigger, binding_context, trigger, templates
            )
            if bound_trigger is not None:
                occupied_triggers.add(bound_trigger.name)
        else:
            bound_trigger = bind_or_record(binding_context, bind_trigger, binding_context, trigger)
        if bound_trigger is not None:
            triggers.append(bound_trigger)
    return triggers
