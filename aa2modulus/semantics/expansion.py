"""Shared typed substitution and bounded local definition composition.

Macro bodies are bound in their own formal scope. Only BoundVariable records
for those formals are substituted, so native meanings never need name rebinding.
No definitions or placeholders reach SIR lowering.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING, NoReturn, cast

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

from ..context.limits import SourceLimits, limit_error, record_children
from ..context.operation import SourceContext
from ..core.locations import RelatedLocation, SourceSpan, with_related
from ..core.source_names import is_source_name
from ..hir import nodes as hir
from ..hir.limits import HIR_NESTED_NODES, HIR_NODES
from ..language.types import CARD
from ..model.types import ValueType
from ..syntax import ast
from ..syntax.walk import walk_ast

type Fail = Callable[[object, str, str], NoReturn]


@dataclass(frozen=True, slots=True)
class MacroTemplate:
    definition: ast.SourceMacro
    body: tuple[hir.BoundStatement, ...]


def definition_order(
    definitions: tuple[ast.SourceMacro, ...], operation: SourceContext, fail: Fail
) -> tuple[ast.SourceMacro, ...]:
    """Validate signatures and return an iterative, cycle-free dependency order."""

    by_name: dict[str, ast.SourceMacro] = {}
    for definition in definitions:
        if not is_source_name(definition.name, allow_qualified=False):
            fail(definition, "MACRO_NAME", f"invalid macro name {definition.name!r}")
        key = definition.name.casefold()
        if key in by_name:
            previous = by_name[key].source_span
            duplicate_notes = (
                ()
                if previous is None
                else (RelatedLocation(previous, "previous macro defined here"),)
            )
            fail(
                replace(
                    definition, source_span=with_related(definition.source_span, duplicate_notes)
                ),
                "DUPLICATE_MACRO",
                f"duplicate macro {definition.name!r}",
            )
        if operation.source_policy.action_candidates(operation.metadata, definition.name):
            fail(
                definition,
                "MACRO_ACTION_COLLISION",
                f"macro {definition.name!r} collides with an action",
            )
        by_name[key] = definition
        _check_formals(definition, fail)
    edges: dict[str, tuple[tuple[str, object], ...]] = {}
    for key, definition in by_name.items():
        edges[key] = tuple(
            (node.name.casefold(), node)
            for node in walk_ast(definition.body)
            if isinstance(node, ast.SourceAction)
            and node.name is not None
            and node.name.casefold() in by_name
        )
    state: dict[str, int] = {}
    ordered: list[ast.SourceMacro] = []
    heights: dict[str, int] = {}
    for root in by_name:
        if state.get(root) == 2:
            continue
        state[root] = 1
        stack = [(root, iter(edges[root]))]
        while stack:
            key, children = stack[-1]
            edge = next(children, None)
            if edge is None:
                height = 1 + max((heights[child] for child, _ in edges[key]), default=0)
                heights[key] = height
                if height > operation.source_limits.max_macro_depth:
                    limit_error(
                        operation.filename,
                        by_name[key].source_span,
                        "MACRO_DEPTH_LIMIT",
                        f"macro call depth exceeds {operation.source_limits.max_macro_depth}",
                    )
                state[key] = 2
                ordered.append(by_name[key])
                stack.pop()
                continue
            child, invocation = edge
            if state.get(child) == 1:
                chain = " -> ".join([item[0] for item in stack] + [child])
                notes = tuple(
                    RelatedLocation(span, f"macro {name!r} defined here")
                    for name, _ in stack
                    if (span := by_name[name].source_span) is not None
                )
                invocation = replace(
                    cast("DataclassInstance", invocation),
                    source_span=with_related(getattr(invocation, "source_span", None), notes),
                )
                fail(invocation, "MACRO_CYCLE", f"recursive macro calls: {chain}")
            if state.get(child) != 2:
                state[child] = 1
                stack.append((child, iter(edges[child])))
    return tuple(ordered)


@dataclass(slots=True)
class ExpansionBudget:
    """Aggregate preparation/instantiation work, checked before output cloning."""

    limits: SourceLimits
    filename: str
    used: int = 0

    def preflight(
        self,
        body: object,
        actuals: dict[str, hir.BoundExpression],
        span: SourceSpan | None,
        *,
        depth: int = 1,
        nesting: int = 0,
        kind: str = "macro",
    ) -> None:
        """Charge the nodes ``body`` expands to before expanding it; a limit error if too many.

        Each replacement expression is counted once per occurrence, without applying
        the template's substitutions to its caller-scoped variable names.
        """

        stack: list[tuple[Iterator[object], int, int, bool]] = [
            (iter((body,)), depth, nesting, True)
        ]
        count = 0
        while stack:
            children, level, nested, substitute = stack[-1]
            try:
                node = next(children)
            except StopIteration:
                stack.pop()
                continue
            if isinstance(node, tuple):
                stack.append((iter(node), level, nested, substitute))
                continue
            if substitute and isinstance(node, hir.BoundVariable) and node.name in actuals:
                stack.append((iter((actuals[node.name],)), level, nested, False))
                continue
            if not isinstance(node, HIR_NODES):
                continue
            count += 1
            if count > self.limits.max_nodes or self.used + count > self.limits.max_expansion_nodes:
                limit_error(
                    self.filename,
                    span,
                    "TEMPLATE_EXPANSION_LIMIT" if kind == "template" else "MACRO_EXPANSION_LIMIT",
                    f"{kind} expansion exceeds the node/work budget",
                )
            if level > self.limits.max_syntax_depth:
                limit_error(
                    self.filename,
                    span,
                    "SOURCE_DEPTH_LIMIT",
                    f"expanded {kind} exceeds syntax depth",
                )
            child_nesting = nested + int(isinstance(node, HIR_NESTED_NODES))
            if child_nesting > self.limits.max_nesting_depth:
                limit_error(
                    self.filename,
                    span,
                    "SOURCE_NESTING_LIMIT",
                    f"expanded {kind} exceeds nesting depth",
                )
            stack.append((record_children(node), level + 1, child_nesting, substitute))
        self.used += count


def _check_formals(definition: ast.SourceMacro, fail: Fail) -> None:
    names: set[str] = set()
    for parameter in definition.parameters:
        if not is_source_name(parameter.name, allow_qualified=False):
            fail(parameter, "MACRO_PARAMETER_NAME", f"invalid formal name {parameter.name!r}")
        if parameter.name in names:
            fail(parameter, "DUPLICATE_MACRO_PARAMETER", f"duplicate formal {parameter.name!r}")
        names.add(parameter.name)
        if parameter.type is not CARD and (
            isinstance(parameter.type, bool)
            or parameter.type
            not in {
                ValueType.INT,
                ValueType.BOOL,
                ValueType.FLOAT,
                ValueType.STRING,
            }
        ):
            fail(
                parameter,
                "MACRO_PARAMETER_TYPE",
                "macro formals require card, int, bool, float, or string",
            )


def substitute_body(
    template: MacroTemplate,
    actuals: dict[str, hir.BoundExpression],
    invocation: SourceSpan | None,
    budget: ExpansionBudget,
    *,
    depth: int,
    nesting: int,
) -> tuple[hir.BoundStatement, ...]:
    """Preflight and instantiate a typed template, retaining lexical identity."""

    return substitute_hir(
        template.body,
        actuals,
        invocation,
        budget,
        depth=depth,
        nesting=nesting,
        kind="macro",
        name=template.definition.name,
    )


def substitute_hir[T](
    nodes: T,
    actuals: dict[str, hir.BoundExpression],
    invocation: SourceSpan | None,
    budget: ExpansionBudget,
    *,
    depth: int,
    nesting: int,
    kind: str,
    name: str,
    renames: dict[str, str] | None = None,
) -> T:
    """Substitute typed values and rename only definition-owned local records."""

    budget.preflight(nodes, actuals, invocation, depth=depth, nesting=nesting, kind=kind)
    local_names = {} if renames is None else renames
    notes = (
        ()
        if invocation is None
        else (
            RelatedLocation(invocation, f"{kind} {name!r} invoked here"),
            *invocation.related,
        )
    )

    def clone(value: object) -> object:
        if isinstance(value, hir.BoundVariable) and value.name in actuals:
            actual = actuals[value.name]
            use = (
                ()
                if value.source_span is None
                else (
                    RelatedLocation(value.source_span, f"formal used in {kind} definition"),
                    *value.source_span.related,
                )
            )
            return annotate(actual, (*use, *notes))
        if isinstance(value, tuple):
            return tuple(clone(item) for item in value)
        if isinstance(value, HIR_NODES):
            updates = {
                field.name: clone(getattr(value, field.name))
                for field in fields(value)
                if field.name != "source_span"
            }
            if hasattr(value, "source_span"):
                updates["source_span"] = with_related(value.source_span, notes)
            if isinstance(value, (hir.BoundVariable, hir.BoundRawVariable, hir.BoundLocal)):
                updates["name"] = local_names.get(value.name, value.name)
            return replace(cast("DataclassInstance", value), **updates)
        return value

    def annotate(value: object, origins: tuple[RelatedLocation, ...]) -> object:
        if isinstance(value, tuple):
            return tuple(annotate(item, origins) for item in value)
        if isinstance(value, HIR_NODES):
            updates = {
                field.name: annotate(getattr(value, field.name), origins)
                for field in fields(value)
                if field.name != "source_span"
            }
            if hasattr(value, "source_span"):
                updates["source_span"] = with_related(value.source_span, origins)
            return replace(cast("DataclassInstance", value), **updates)
        return value

    return cast(T, clone(nodes))
