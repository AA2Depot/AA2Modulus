"""Editor references and constants over partial source."""

from __future__ import annotations

import contextlib
from dataclasses import fields
from typing import cast

from ...context.operation import SourceContext
from ...hir.limits import BindingBudget
from ...hir.symbols import BoundReference, ResolvedConstant, SourceDeclaration
from ...language.types import (
    SourceType,
)
from ...syntax.ast import (
    STATEMENT_TYPES,
    SourceBinary,
    SourceCall,
    SourceCardConversion,
    SourceConstantReference,
    SourceEvent,
    SourceExpression,
    SourceGroup,
    SourceLiteral,
    SourceMacro,
    SourceMemberCall,
    SourceMemberProperty,
    SourceModule,
    SourceName,
    SourceRawExpression,
    SourceStatement,
    SourceTrigger,
    SourceTriggerImport,
    SourceTriggerTemplate,
    SourceUnary,
    SourceUnit,
    SourceVariableReference,
)
from ...syntax.limits import check_source_ast
from ..expansion import (
    ExpansionBudget,
    MacroTemplate,
)
from .constants import authoring_constants, global_value
from .expressions import bind_expression
from .reporting import record_constant_reference, record_reference
from .state import BindContext, SourceBindingError
from .statements import bind_event, bind_statement


def bind_authoring_references(
    unit: SourceUnit, operation: SourceContext
) -> tuple[BoundReference, ...]:
    """Keep successful selections around unrelated input errors.

    This view reuses the binder's expression/statement rules and contexts. Empty
    macro bodies make reference collection independent of expansion, while the
    authored definition still supplies each call's signature and target.
    """

    check_source_ast(unit, filename=operation.filename, limits=operation.source_limits)
    scope = _AuthoringScope(operation, unit)
    top_resolved, module_resolved = authoring_constants(unit, operation)
    top_table = {item.declaration.name: item for item in top_resolved}
    all_table = {**top_table, **{item.declaration.name: item for item in module_resolved}}
    _constant_links((*top_resolved, *module_resolved), all_table, scope.references)
    for macro in unit.macros:
        isolated = scope.context(
            {},
            {item.name: item.type for item in macro.parameters},
            local_declarations={item.name: item for item in macro.parameters},
            macro=macro,
            constants=top_table,
        )
        _collect(isolated, macro.body)
    for template in unit.templates:
        isolated = scope.context(
            {},
            {item.name: item.type for item in template.slots},
            local_declarations={item.name: item for item in template.slots},
            template=template,
            constants=top_table,
        )
        _trigger(isolated, template.trigger)
    if unit.module is not None:
        _module(unit, unit.module, scope, all_table)
    return tuple(dict.fromkeys(scope.references))


class _AuthoringScope:
    """Contexts sharing one reference list, binding budget and empty-bodied macros."""

    def __init__(self, operation: SourceContext, unit: SourceUnit) -> None:
        self.operation = operation
        self.references: list[BoundReference] = []
        self.binding_budget = BindingBudget(operation.source_limits, operation.filename)
        self.macros: dict[str, MacroTemplate] = {}
        for macro_definition in unit.macros:
            self.macros.setdefault(
                macro_definition.name.casefold(), MacroTemplate(macro_definition, ())
            )

    def context(
        self,
        globals_: dict[str, SourceType],
        locals_: dict[str, SourceType],
        *,
        global_declarations: dict[str, SourceDeclaration] | None = None,
        local_declarations: dict[str, SourceDeclaration] | None = None,
        macro: SourceMacro | None = None,
        template: SourceTriggerTemplate | None = None,
        constants: dict[str, ResolvedConstant] | None = None,
    ) -> BindContext:
        operation = self.operation
        return BindContext(
            operation.metadata,
            operation.source_policy,
            operation.filename,
            globals_,
            locals_,
            global_declarations=global_declarations or {},
            local_declarations=local_declarations or {},
            macros=self.macros,
            macro_definition=macro,
            template_definition=template,
            expansion_budget=ExpansionBudget(operation.source_limits, operation.filename),
            references=self.references,
            catalog=operation.catalog,
            binding_budget=self.binding_budget,
            constants=constants or {},
        )


def _constant_links(
    entries: tuple[ResolvedConstant, ...],
    all_table: dict[str, ResolvedConstant],
    references: list[BoundReference],
) -> None:
    """Constant-to-constant links are part of the authoring view, too."""

    for entry in entries:
        if entry.value is not None and not isinstance(entry.declaration.value, SourceLiteral):
            target = all_table.get(entry.declaration.value.name)
            if target is not None and (target.top_level or not entry.top_level):
                record_constant_reference(
                    references, entry.declaration.value.name, entry.declaration.value, target
                )


def _collect(context: BindContext, nodes: object, expected: SourceType | None = None) -> None:
    pending = [(nodes, expected)]
    while pending:
        node, value_type = pending.pop()
        if isinstance(node, tuple):
            pending.extend((item, None) for item in reversed(node))
            continue
        try:
            if isinstance(node, SourceEvent):
                bind_event(context, node)
            elif isinstance(node, STATEMENT_TYPES):
                bind_statement(context, node)
            elif isinstance(
                node,
                (
                    SourceLiteral,
                    SourceName,
                    SourceCall,
                    SourceMemberCall,
                    SourceMemberProperty,
                    SourceUnary,
                    SourceBinary,
                    SourceGroup,
                    SourceCardConversion,
                    SourceVariableReference,
                    SourceConstantReference,
                    SourceRawExpression,
                ),
            ):
                bind_expression(context, node, value_type)
            else:
                continue
        except SourceBindingError:
            # Failed parents can contain independently useful complete
            # children. Their own native selection still goes through the
            # same binder, rather than a second name-resolution system.
            pending.extend(
                (getattr(node, item.name), None)
                for item in reversed(
                    fields(cast(SourceEvent | SourceStatement | SourceExpression, node))
                )
                if item.name not in {"source_span", "name_span", "target_span"}
            )


def _trigger(context: BindContext, trigger: SourceTrigger) -> None:
    for local in trigger.locals:
        context.locals.setdefault(local.name, local.type)
        context.local_declarations.setdefault(local.name, local)
    _collect(context, trigger.events)
    for local in trigger.locals:
        _collect(context, local.default, local.type)
    _collect(context, trigger.statements)


def _module(
    unit: SourceUnit,
    module: SourceModule,
    scope: _AuthoringScope,
    all_table: dict[str, ResolvedConstant],
) -> None:
    globals_: dict[str, SourceType] = {}
    declarations: dict[str, SourceDeclaration] = {}
    for global_ in module.globals:
        globals_.setdefault(global_.name, global_.type)
        declarations.setdefault(global_.name, global_)
    initializers = scope.context(globals_, {}, constants=all_table)
    for global_ in module.globals:
        if isinstance(global_.default, (SourceName, SourceConstantReference)):
            with contextlib.suppress(SourceBindingError):
                global_value(initializers, global_.default)
    for item in module.triggers:
        context = scope.context(globals_, {}, global_declarations=declarations, constants=all_table)
        if isinstance(item, SourceTrigger):
            _trigger(context, item)
        else:
            _template_import(context, unit, item)


def _template_import(context: BindContext, unit: SourceUnit, item: SourceTriggerImport) -> None:
    template_definition = next(
        (candidate for candidate in unit.templates if candidate.name == item.template),
        None,
    )
    if template_definition is not None:
        record_reference(context, item.template, item, declaration=template_definition)
    for slot in item.slots:
        parameter = (
            None
            if template_definition is None
            else next((p for p in template_definition.slots if p.name == slot.name), None)
        )
        if parameter is not None:
            record_reference(
                context,
                slot.name,
                slot,
                declaration=parameter,
                value_type=parameter.type,
            )
        _collect(context, slot.value)
