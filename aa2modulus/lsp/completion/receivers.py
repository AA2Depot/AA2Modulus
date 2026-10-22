"""Receiver typing and configured member forms for ``receiver.Member`` sites."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lark import Token

from ...context.operation import SourceContext
from ...language.values import MemberForm
from ...model.types import ValueType
from .tokens import NAME_TOKENS


@dataclass(frozen=True, slots=True)
class MemberSite:
    """A cursor after ``receiver.`` where configured member forms apply."""

    statement: bool
    receiver_type: int | None
    expected_type: int | None
    partial: str
    partial_start: int


def _property_type(
    context: SourceContext, member: str, receiver_type: int | None
) -> tuple[bool, int | None]:
    """Whether ``member`` is a property of the receiver, and its result type if unique."""

    forms = [
        form
        for form in context.catalog.member_forms(member, kind="expression", arguments=0)
        if receiver_type is None or form.receiver_type == receiver_type
    ]
    results = {form.result_type for form in forms}
    return bool(forms), (results.pop() if len(results) == 1 else None)


def _path_type(
    parts: Sequence[str], visible: Mapping[str, int], context: SourceContext
) -> tuple[bool, int | None]:
    """Resolve a dotted path as a receiver using the binder's rules.

    The path is a declared variable, a registered zero-argument ``int``
    built-in (``ThisCard``, ``TriggeringCard``) or a property chain on
    one of those. Namespace roots are exact static paths and never variables.
    """

    catalog = context.catalog
    name = ".".join(parts)
    if (
        len(parts) == 1
        and parts[0] in visible
        and parts[0] not in catalog.namespace_roots
        and parts[0].casefold() not in catalog.protected_names
    ):
        return True, visible[parts[0]]
    if any(
        not entry.parameter_types and entry.return_type == ValueType.INT
        for entry in catalog.expression_candidates(name)
    ):
        return True, ValueType.INT
    if len(parts) == 1:
        return False, None
    ok, receiver_type = _path_type(parts[:-1], visible, context)
    if not ok:
        return False, None
    return _property_type(context, parts[-1], receiver_type)


def _quoted_receiver_type(receiver: tuple[Token, ...], visible: Mapping[str, int]) -> int | None:
    """Declared type of a ``variable("name")`` receiver; other receivers are not typed."""

    if len(receiver) != 4 or receiver[0].type != "VARIABLE" or receiver[2].type != "ESCAPED_STRING":
        return None
    try:
        name = json.loads(str(receiver[2]))
    except ValueError:
        return None
    return visible.get(name) if isinstance(name, str) else None


def _receiver_chain(
    tokens: tuple[Token, ...], end: int, visible: Mapping[str, int], context: SourceContext
) -> tuple[int, int | None] | None:
    """Start index and declared type of the receiver expression ending at ``tokens[end]``.

    A receiver is a name path, ``variable("x")``, ``(expr)`` or a call, followed
    by any number of ``.Member`` / ``.Member(...)`` postfix steps.
    """

    if end < 0:
        return None
    last = tokens[end]
    call = False
    if last.type == "RPAR":
        depth = 0
        opening = -1
        for position in range(end, -1, -1):
            if tokens[position].type == "RPAR":
                depth += 1
            elif tokens[position].type == "LPAR":
                depth -= 1
                if depth == 0:
                    opening = position
                    break
        if opening < 0:
            return None
        start = opening
        if opening > 0 and (
            tokens[opening - 1].type in NAME_TOKENS or tokens[opening - 1].type == "VARIABLE"
        ):
            start = opening - 1
        call = True
    elif last.type in NAME_TOKENS:
        start = end
    else:
        return None
    first = tokens[start]
    follows_dot = start > 0 and tokens[start - 1].type == "DOT"
    if first.type in NAME_TOKENS and follows_dot:
        # A member step: its receiver is everything before the dot.
        inner = _receiver_chain(tokens, start - 2, visible, context)
        if inner is None:
            return None
        receiver_type = inner[1]
        parts = str(first).split(".")
        for index, part in enumerate(parts):
            if call and index == len(parts) - 1:
                receiver_type = None
                break
            ok, receiver_type = _property_type(context, part, receiver_type)
            if not ok:
                return None
        return inner[0], receiver_type
    if call:
        if first.type == "VARIABLE":
            return start, _quoted_receiver_type(tokens[start : end + 1], visible)
        return start, None
    ok, receiver_type = _path_type(str(first).split("."), visible, context)
    return (start, receiver_type) if ok else None


def receiver(
    before: tuple[Token, ...],
    path: Sequence[str],
    visible: Mapping[str, int],
    context: SourceContext,
) -> tuple[int, int | None] | None:
    """Receiver of a member whose dotted ``path`` follows ``before``.

    Returns the index in ``before`` where the receiver starts and its type.
    """

    if before and before[-1].type == "DOT":
        chain = _receiver_chain(before, len(before) - 2, visible, context)
        if chain is None:
            return None
        start, receiver_type = chain
        for part in path:
            ok, receiver_type = _property_type(context, part, receiver_type)
            if not ok:
                return None
        return start, receiver_type
    if not path:
        return None
    ok, receiver_type = _path_type(path, visible, context)
    return (len(before), receiver_type) if ok else None


def member_forms(
    context: SourceContext, site: MemberSite, *, member: str | None = None
) -> list[MemberForm]:
    """Configured forms valid at ``site``, in policy order."""

    kind = "action" if site.statement else "expression"
    return [
        form
        for form in context.catalog.policy.member_forms
        if form.target.kind == kind
        and (member is None or form.name.casefold() == member.casefold())
        and (site.receiver_type is None or form.receiver_type == site.receiver_type)
        and (site.statement or site.expected_type is None or form.result_type == site.expected_type)
    ]
