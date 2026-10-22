"""Compile-time constants: resolution, references and global initializers."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, NoReturn

from ...context.operation import SourceContext
from ...core.diagnostics import SourceFix
from ...core.locations import RelatedLocation, with_related
from ...hir.limits import BindingBudget
from ...hir.nodes import (
    BoundLiteral,
)
from ...hir.symbols import ResolvedConstant
from ...model.types import TypeId, ValueType
from ...model.values import Value
from ...syntax.ast import (
    SourceConstant,
    SourceConstantReference,
    SourceLiteral,
    SourceName,
    SourceUnit,
)
from ...syntax.limits import check_source_ast
from .declarations import check_protected_declaration
from .reporting import name_span_of, node_span, raise_error, record_constant_reference
from .state import BindContext, Poisoned, SourceBindingError
from .suggestions import hidden_help, hidden_hint
from .values import check_type, literal_value


def constant_entry(
    context: BindContext,
    name: str,
    node: object,
    *,
    use: Literal["read", "assignment", "target"] = "read",
) -> ResolvedConstant | None:
    """The visible constant a bare name selects, rejecting a clash with a variable.

    A read may mean either; an assignment target can only be ``variable("...")``;
    other targets (for loops, Set Variable) take no explicit form, so get no fix.
    """

    entry = context.constants.get(name)
    if entry is None:
        return None
    if context.variable_type(name) is not None:
        span = name_span_of(node)
        spellings = {
            "read": (f'const("{name}")', f'variable("{name}")'),
            "assignment": (f'variable("{name}")',),
            "target": (),
        }[use]
        raise_error(
            context,
            node,
            "AMBIGUOUS_CONST",
            f"name {name!r} is both a constant and a variable",
            help=f'write const("{name}") or variable("{name}")',
            fixes=()
            if span is None
            else tuple(SourceFix(f"Write {text}", span, text) for text in spellings),
        )
    return entry


def bind_constant(
    context: BindContext, entry: ResolvedConstant, node: object, expected: TypeId | None
) -> BoundLiteral:
    """Substitute the constant's literal, carrying the reference's own source span."""

    if entry.value is None:
        if context.collector is not None:
            raise Poisoned
        raise_error(
            context,
            node,
            "UNDEFINED_CONST",
            f"constant {entry.declaration.name!r} could not be resolved",
        )
    check_type(context, entry.type, expected, node)
    span = node_span(node)
    record_constant_reference(context.references, entry.declaration.name, node, entry)
    return BoundLiteral(replace(entry.value, source_span=span), source_span=span)


def bind_constant_reference(
    context: BindContext, name: str, node: object, expected: TypeId | None
) -> BoundLiteral:
    entry = context.constants.get(name)
    if entry is None:
        raise_error(
            context,
            node,
            "UNDEFINED_CONST",
            f"undefined constant {name!r}{hidden_hint(context, name)}",
            help=hidden_help(context, name) or None,
        )
    return bind_constant(context, entry, node, expected)


_CONSTANT_TYPES = frozenset({ValueType.INT, ValueType.BOOL, ValueType.FLOAT, ValueType.STRING})


def resolve_constants(
    context: BindContext,
    top_level: tuple[SourceConstant, ...],
    module_level: tuple[SourceConstant, ...],
    *,
    strict: bool = True,
) -> dict[str, ResolvedConstant]:
    """Resolve every constant to a typed literal, independent of declaration order.

    Top-level constants see only top-level constants; module constants see both.
    With ``strict=False`` (editor views) failing constants are skipped or left
    unresolved instead of raising. With a collector, each failing constant is
    recorded and left unresolved, so its uses report nothing further.
    Const-to-const references are iterative.
    """

    declarations, failed = _declare_constants(context, top_level, module_level, strict=strict)
    resolved: dict[str, ResolvedConstant] = {}
    for root, _ in tuple(declarations.values()):
        _resolve_root(context, root, declarations, failed, resolved, strict=strict)
    for name, (item, is_top) in failed.items():
        resolved.setdefault(name, ResolvedConstant(item, item.type, None, is_top))
    return resolved


type _Declarations = dict[str, tuple[SourceConstant, bool]]


def _declare_constants(
    context: BindContext,
    top_level: tuple[SourceConstant, ...],
    module_level: tuple[SourceConstant, ...],
    *,
    strict: bool,
) -> tuple[_Declarations, _Declarations]:
    """Declared constants (and whether each is top-level), and the ones that failed."""

    declarations: _Declarations = {}
    failed: _Declarations = {}
    for item, is_top in (
        *((item, True) for item in top_level),
        *((item, False) for item in module_level),
    ):
        try:
            _check_declaration(context, item, declarations)
        except SourceBindingError as exc:
            if not strict:
                continue
            if context.collector is None:
                raise
            context.collector.record(exc)
            failed.setdefault(item.name, (item, is_top))
            continue
        declarations[item.name] = (item, is_top)
    return declarations, failed


def _check_declaration(
    context: BindContext, item: SourceConstant, declarations: _Declarations
) -> None:
    context.binding_budget.charge(node_span(item))
    if not item.name:
        raise_error(context, item, "CONST_NAME", "constant names cannot be empty")
    check_protected_declaration(context, item, serialized=False)
    if isinstance(item.type, bool) or item.type not in _CONSTANT_TYPES:
        raise_error(context, item, "CONST_TYPE", "constants require int, bool, float, or string")
    if item.name in declarations:
        previous = declarations[item.name][0].source_span
        notes: tuple[RelatedLocation, ...] = (
            () if previous is None else (RelatedLocation(previous, "previous constant"),)
        )
        raise_error(
            context,
            replace(item, source_span=with_related(item.source_span, notes)),
            "DUPLICATE_CONST",
            f"duplicate constant {item.name!r}",
        )


def _resolve_root(
    context: BindContext,
    root: SourceConstant,
    declarations: _Declarations,
    failed: _Declarations,
    resolved: dict[str, ResolvedConstant],
    *,
    strict: bool,
) -> None:
    """Follow const-to-const references from ``root`` to a literal, then fill the chain."""

    chain: list[SourceConstant] = []
    in_chain: set[str] = set()
    current = root
    try:
        while current.name not in resolved:
            value = current.value
            is_top = declarations[current.name][1]
            if isinstance(value, SourceLiteral):
                literal = literal_value(context, value)
                check_type(context, literal.type, current.type, value)
                resolved[current.name] = ResolvedConstant(current, current.type, literal, is_top)
                break
            target = declarations.get(value.name)
            if target is None and value.name in failed and context.collector is not None:
                raise Poisoned
            if target is None or (is_top and not target[1]):
                hint = "" if target is None else " (module constants are not visible here)"
                raise_error(
                    context,
                    value,
                    "UNDEFINED_CONST",
                    f"undefined constant {value.name!r}{hint}",
                )
            in_chain.add(current.name)
            if value.name in in_chain:
                _cycle_error(context, [*chain, current], value)
            chain.append(current)
            current = target[0]
        _fill_chain(context, chain, declarations, resolved)
    except (SourceBindingError, Poisoned) as exc:
        if strict and context.collector is None:
            raise
        if isinstance(exc, SourceBindingError) and context.collector is not None:
            context.collector.record(exc)
        for item in (*chain, current):
            resolved.setdefault(
                item.name, ResolvedConstant(item, item.type, None, declarations[item.name][1])
            )


def _cycle_error(
    context: BindContext, path: list[SourceConstant], value: SourceConstantReference | SourceName
) -> NoReturn:
    cycle = path[[item.name for item in path].index(value.name) :]
    notes = tuple(
        RelatedLocation(span, f"constant {item.name!r} declared here")
        for item in cycle
        if (span := item.source_span) is not None
    )
    names = " -> ".join([*(item.name for item in cycle), value.name])
    raise_error(
        context,
        replace(value, source_span=with_related(value.source_span, notes)),
        "CONST_CYCLE",
        f"cyclic constants: {names}",
    )


def _fill_chain(
    context: BindContext,
    chain: list[SourceConstant],
    declarations: _Declarations,
    resolved: dict[str, ResolvedConstant],
) -> None:
    """Give each constant on the followed chain its target's value, last first."""

    for item in reversed(chain):
        value = item.value
        assert not isinstance(value, SourceLiteral)
        is_top = declarations[item.name][1]
        target_entry = resolved[value.name]
        if target_entry.value is None:
            resolved[item.name] = ResolvedConstant(item, item.type, None, is_top)
            continue
        check_type(context, target_entry.type, item.type, value)
        record_constant_reference(context.references, value.name, value, target_entry)
        resolved[item.name] = ResolvedConstant(item, item.type, target_entry.value, is_top)


def authoring_constants(
    unit: SourceUnit, operation: SourceContext
) -> tuple[tuple[ResolvedConstant, ...], tuple[ResolvedConstant, ...]]:
    """Editor view of ``(top_level, module_level)`` constants; failures are left unresolved."""

    check_source_ast(unit, filename=operation.filename, limits=operation.source_limits)
    context = BindContext(
        operation.metadata,
        operation.source_policy,
        operation.filename,
        {},
        {},
        catalog=operation.catalog,
        binding_budget=BindingBudget(operation.source_limits, operation.filename),
    )
    module_items = () if unit.module is None else unit.module.constants
    resolved = resolve_constants(context, unit.constants, module_items, strict=False)
    return (
        tuple(item for item in resolved.values() if item.top_level),
        tuple(item for item in resolved.values() if not item.top_level),
    )


def global_value(
    context: BindContext, node: SourceLiteral | SourceName | SourceConstantReference
) -> Value:
    """A global initializer: a literal, or a constant reference substituted in place."""

    if isinstance(node, SourceLiteral):
        return literal_value(context, node)
    return bind_constant_reference(context, node.name, node, None).value
