"""Protected names and constant/variable collisions."""

from __future__ import annotations

from dataclasses import replace

from ...core.locations import RelatedLocation, with_related
from ...hir.symbols import ResolvedConstant
from ...syntax.ast import (
    SourceConstant,
    SourceGlobal,
    SourceLocal,
    SourceParameter,
)
from .reporting import node_span, raise_error
from .state import BindContext


def is_protected(context: BindContext, name: str) -> bool:
    return name.casefold() in context.catalog.protected_names


def protected_message(name: str) -> str:
    return f"{name!r} is a protected built-in name"


def protected_help(name: str) -> str:
    return (
        f'quote the declaration ("{name}") and reference it with variable("{name}") '
        "to name a native variable"
    )


def check_protected_declaration(
    context: BindContext,
    node: SourceGlobal | SourceLocal | SourceParameter | SourceConstant,
    *,
    serialized: bool,
) -> None:
    """Reject a protected name as a declaration, allowing quoted serialized variables."""

    if not is_protected(context, node.name):
        return
    if serialized and node.quoted_name:
        return
    if serialized:
        raise_error(
            context,
            node,
            "PROTECTED_NAME",
            protected_message(node.name),
            help=protected_help(node.name),
        )
    raise_error(
        context,
        node,
        "PROTECTED_NAME",
        f"{node.name!r} is a protected built-in name and cannot name a non-variable",
    )


def check_constant_collision(
    context: BindContext,
    name: str,
    node: SourceGlobal | SourceLocal | SourceParameter,
    what: str,
    constants: dict[str, ResolvedConstant] | None = None,
) -> None:
    """A declared name may not equal a constant that is visible where it is declared."""

    entry = (context.constants if constants is None else constants).get(name)
    if entry is None:
        return
    declared = entry.declaration.source_span
    notes = () if declared is None else (RelatedLocation(declared, "constant declared here"),)
    raise_error(
        context,
        replace(node, source_span=with_related(node_span(node), notes)),
        "CONST_NAME_COLLISION",
        f"{what} {name!r} collides with a visible constant of the same name",
    )
