"""Help for unknown, hidden, retired and wrong-case names."""

from __future__ import annotations

from typing import Literal

from ...metadata.identities import NativeKind
from ...syntax.ast import (
    SourceExpression,
)
from .rewrites import member_rewrites
from .state import BindContext


def hidden_hint(context: BindContext, name: str) -> str:
    if name not in context.hidden_constants:
        return ""
    return f"; module constant {name!r} is not visible in macros or templates"


def hidden_help(context: BindContext, name: str) -> str:
    return "declare it at top level" if name in context.hidden_constants else ""


def root_hint(context: BindContext, name: str, *kinds: NativeKind) -> str:
    """Suffix for unknown-name messages when only the namespace root's case is wrong.

    Names the whole canonical spelling when the tail resolves under ``kinds``;
    otherwise only the root is corrected and the tail is left as typed.
    """

    if context.catalog is None:
        return ""
    root = context.catalog.root_case_variant(name)
    if root is None:
        return ""
    exact = context.catalog.case_rewrite(name, *kinds) or root + name[len(root) :]
    return f"namespace roots are case-sensitive; did you mean {exact!r}?"


def retired_hint(
    context: BindContext,
    name: str,
    *kinds: NativeKind,
    arguments: tuple[SourceExpression, ...] | None = None,
) -> str:
    """Suffix naming the canonical replacement for a retired native spelling.

    ``arguments`` are the rejected call's source arguments; with them a card-first
    flat call is rewritten as the member form it should have used.
    """

    if context.catalog is None:
        return ""
    names = context.catalog.retired_names(name, *kinds)
    if not names and context.catalog.root_case_variant(name) is None:
        names = _member_spellings(context, name, kinds, arguments)
    if not names:
        return ""
    return "use " + " or ".join(repr(item) for item in names)


def _member_spellings(
    context: BindContext,
    name: str,
    kinds: tuple[NativeKind, ...],
    arguments: tuple[SourceExpression, ...] | None = None,
) -> tuple[str, ...]:
    """Receiver spellings that replace a rejected flat name (card-first targets)."""

    member_kinds: list[Literal["action", "expression"]] = []
    if "action" in kinds:
        member_kinds.append("action")
    if "expression" in kinds or "named_constant" in kinds:
        member_kinds.append("expression")
    forms = context.catalog.retired_member_forms(name, *member_kinds)
    if arguments and (precise := member_rewrites(forms, arguments)):
        return precise
    return tuple(
        dict.fromkeys(
            f"<card>.{form.name}"
            if form.target.kind == "expression" and not form.arguments
            else f"<card>.{form.name}(...)"
            for form in forms
        )
    )
