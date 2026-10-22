"""Format a serialized module as unified source text."""

from __future__ import annotations

from collections.abc import Mapping

from ...context.operation import SourceContext
from ...core.diagnostics import Diagnostic
from ...core.locations import PathPart
from ...metadata.snapshot import MetadataSnapshot
from ...model.records import GlobalVariable, Module, Trigger, Variable
from ...model.types import TypeId, ValueType
from .cards import card_text
from .context import (
    FormatContext,
    declaration_name,
)
from .expressions import expression_text
from .inference import CardInference, CardKey
from .statements import action_sequence_lines, event_line
from .text import FormatError, declaration_type, literal, quote, raw_value


def format_module_with_diagnostics(
    module: Module,
    *,
    metadata: MetadataSnapshot | None = None,
    context: SourceContext | None = None,
    allows: Mapping[tuple[PathPart, ...], tuple[str, ...]] | None = None,
) -> tuple[str, tuple[Diagnostic, ...]]:
    """Format once and return diagnostics from decisions that emitted raw syntax.

    ``allows`` maps binary node paths to codes emitted as ``@allow`` before them.
    """

    operation = SourceContext.resolve(
        context,
        metadata=metadata,
    )
    resolved = operation.metadata.resolve_module(module)
    diagnostics: list[Diagnostic] = []
    format_context = FormatContext(
        operation.metadata,
        operation.source_policy,
        operation.catalog,
        {},
        operation.filename,
        diagnostics,
        dict(allows or {}),
    )
    global_types, scopes, own = _scopes(resolved)
    cards = CardInference(resolved, format_context, (*scopes, dict(global_types)), own).infer()
    lines = format_context.allow_lines((resolved,), 0)
    lines.append(f"module {quote(resolved.name)} {{")
    if resolved.description:
        lines.append(f"  description {quote(resolved.description)};")
    for dependency in resolved.dependencies:
        lines.append(f"  depends_on {quote(dependency)};")
    for global_variable in resolved.globals:
        lines.extend(_global_lines(global_variable, cards, format_context))
    for index, trigger in enumerate(resolved.triggers):
        lines.append("")
        lines.extend(_trigger_lines(index, trigger, scopes[index], cards, format_context))
    lines.append("}")
    return "\n".join(lines) + "\n", tuple(diagnostics)


def _scopes(resolved: Module) -> tuple[dict[str, TypeId], list[dict[str, TypeId]], set[str]]:
    """The global types, each trigger's variable scope and the module's own int globals."""

    global_types: dict[str, TypeId] = {}
    for global_variable in resolved.globals:
        global_types.setdefault(global_variable.name, global_variable.type)
    scopes: list[dict[str, TypeId]] = []
    for trigger in resolved.triggers:
        scope = dict(global_types)
        for local_variable in trigger.variables:
            scope.setdefault(local_variable.name, local_variable.type)
        scopes.append(scope)
    # The last scope holds globals only, so a local shadowed by a global is never a candidate.
    own = {
        item.name
        for item in resolved.globals
        if item.type == ValueType.INT and global_types.get(item.name) == ValueType.INT
    }
    return global_types, scopes, own


def _global_lines(
    global_variable: GlobalVariable, cards: frozenset[CardKey], context: FormatContext
) -> list[str]:
    declared_type = declaration_type(global_variable.type, "global", global_variable.name)
    if (None, global_variable.name) in cards:
        declared_type = "card"
    if (
        global_variable.default_value.type != global_variable.type
        or global_variable.current_value.type != global_variable.type
    ):
        raise FormatError(
            f"global {global_variable.name!r} has value types that its declaration cannot preserve"
        )
    name = declaration_name(global_variable.name, context)
    if (
        global_variable.current_value == global_variable.default_value
        and not global_variable.initialized
        and global_variable.default_value.type is not ValueType.INVALID
    ):
        return [f"  global {name}: {declared_type} = {literal(global_variable.default_value)};"]
    return [
        f"  global {name}: {declared_type} {{",
        f"    default {raw_value(global_variable.default_value)};",
        f"    current {raw_value(global_variable.current_value)};",
        f"    initialized {'true' if global_variable.initialized else 'false'};",
        "  }",
    ]


def _trigger_lines(
    index: int,
    trigger: Trigger,
    scope: dict[str, TypeId],
    cards: frozenset[CardKey],
    context: FormatContext,
) -> list[str]:
    lines = context.allow_lines((trigger,), 2)
    lines.append(f"  trigger {quote(trigger.name)} {{")
    context.variables = scope
    context.cards = frozenset(name for owner, name in cards if owner is None or owner == index)
    for event in trigger.events:
        lines.extend(context.allow_lines((event,), 4))
        lines.append(event_line(event, context, 4))
    for local_variable in trigger.variables:
        lines.extend(_local_lines(index, local_variable, cards, context))
    lines.extend(action_sequence_lines(trigger.gui_actions, context, 4))
    lines.append("  }")
    return lines


def _local_lines(
    index: int, local_variable: Variable, cards: frozenset[CardKey], context: FormatContext
) -> list[str]:
    declared_type = declaration_type(local_variable.type, "local", local_variable.name)
    if local_variable.default_expression.return_type != local_variable.type:
        raise FormatError(
            f"local {local_variable.name!r} has a default expression type that its "
            "declaration cannot preserve"
        )
    default = expression_text(
        local_variable.default_expression,
        context,
        expected_type=local_variable.type,
    )
    if (index, local_variable.name) in cards:
        declared_type = "card"
        default = card_text(local_variable.default_expression, default, context)
    lines = context.allow_lines((local_variable,), 4)
    lines.append(
        f"    let {declaration_name(local_variable.name, context)}: {declared_type} = {default};"
    )
    return lines


def format_module(
    module: Module,
    *,
    metadata: MetadataSnapshot | None = None,
    context: SourceContext | None = None,
) -> str:
    """Format a serialized module as one deterministic unified source file."""

    source, _diagnostics = format_module_with_diagnostics(
        module,
        metadata=metadata,
        context=context,
    )
    return source
