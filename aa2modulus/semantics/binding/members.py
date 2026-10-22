"""Receiver forms of member calls and actions."""

from __future__ import annotations

from ...core.locations import SourceSpan
from ...language.values import MemberForm
from ...model.display import type_name
from ...model.types import TypeId, ValueType
from ...syntax.ast import (
    SourceExpression,
    SourceMemberProperty,
    SourceName,
)
from ...syntax.spans import qualified_segment_spans
from .reporting import raise_error
from .rewrites import join_segment_spans, receiver_text
from .state import BindContext


def dotted_receiver(
    context: BindContext, name: str, name_span: SourceSpan | None
) -> tuple[SourceExpression, str, SourceSpan | None] | None:
    """Split an unregistered dotted token into a receiver and its final member.

    Registered names are tried before this runs. The receiver is the longest
    path before the last segment that is a declared variable, a registered
    zero-argument ``int`` built-in (``ThisCard``, ``TriggeringCard``) or
    a property chain on one of those. Namespace roots are exact, case-sensitive
    static paths, so adding a variable never retargets ``Context.Unknown`` or an
    existing built-in; ``variable("Context").Member`` selects such a variable.
    """

    parts = name.split(".")
    if len(parts) < 2:
        return None
    spans = qualified_segment_spans(name, name_span)
    receiver = _path_receiver(context, parts[:-1], spans[:-1])
    if receiver is None:
        return None
    return receiver, parts[-1], spans[-1]


def _path_receiver(
    context: BindContext, parts: list[str], spans: tuple[SourceSpan | None, ...]
) -> SourceExpression | None:
    name = ".".join(parts)
    span = join_segment_spans(spans[0], spans[-1])
    if (
        len(parts) == 1
        and (context.variable_type(name) is not None or name in context.constants)
        and name not in context.catalog.namespace_roots
        and name.casefold() not in context.catalog.protected_names
    ):
        # A variable or constant wins over a same-named built-in, except protected names.
        return SourceName(name, source_span=span, name_span=span)
    if any(
        not entry.parameter_types and entry.return_type == ValueType.INT
        for entry in context.catalog.expression_candidates(name)
    ):
        return SourceName(name, source_span=span, name_span=span)
    if len(parts) == 1:
        return None
    inner = _path_receiver(context, parts[:-1], spans[:-1])
    if inner is None:
        return None
    return SourceMemberProperty(
        inner,
        parts[-1],
        source_span=span,
        name_span=spans[-1],
    )


def bind_member_form(
    context: BindContext,
    node: object,
    receiver: SourceExpression,
    member: str,
    arguments: int | None,
    *,
    action: bool,
    expected: TypeId | None,
) -> MemberForm:
    """Select the member form; ``arguments`` is ``None`` for a property read (no parentheses)."""

    configured = context.catalog.member_forms(member)
    shown = receiver_text(receiver)
    if not configured:
        replacements = context.catalog.retired_member_names(
            member, "action" if action else "expression"
        )
        raise_error(
            context,
            node,
            "UNKNOWN_MEMBER",
            f"unknown member {member!r}",
            help="use " + " or ".join(repr(item) for item in replacements)
            if replacements
            else None,
        )
    kind = "action" if action else "expression"
    forms = tuple(form for form in configured if form.target.kind == kind)
    if not forms:
        raise_error(
            context,
            node,
            "MEMBER_KIND",
            f"member {member!r} is "
            + ("a value and cannot be a statement" if action else "an action and returns no value"),
            help=None if arguments is not None else f"write '{shown}.{member}(...)' as a statement",
        )
    count = 0 if arguments is None else arguments
    exact = tuple(form for form in forms if len(form.arguments) == count)
    if not exact:
        if arguments is None:
            raise_error(
                context,
                node,
                "MEMBER_ARITY",
                f"member {member!r} takes arguments",
                help=f"write '{shown}.{member}(...)'",
            )
        raise_error(
            context, node, "MEMBER_ARITY", f"member {member!r} has the wrong argument count"
        )
    forms = exact
    if arguments is not None and count == 0 and not action:
        raise_error(
            context,
            node,
            "MEMBER_KIND",
            f"member {member!r} is a property and takes no parentheses",
            help=f"write '{shown}.{member}'",
        )
    if expected is not None and not action:
        forms = tuple(form for form in forms if form.result_type == expected)
        if not forms:
            raise_error(
                context,
                node,
                "SOURCE_TYPE_MISMATCH",
                f"member {member!r} has no overload returning {type_name(expected)}",
            )
    if len(forms) > 1:
        raise_error(context, node, "AMBIGUOUS_MEMBER", f"ambiguous member {member!r}")
    return forms[0]
