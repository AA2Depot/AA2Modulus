"""Source text rewrites behind quick fixes."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import Literal, cast

from ...core.diagnostics import SourceFix
from ...core.locations import SourceSpan
from ...language.values import MemberForm
from ...metadata.identities import NativeKind
from ...syntax.ast import (
    FloatBitsLiteral,
    SourceAction,
    SourceBinary,
    SourceCall,
    SourceCardConversion,
    SourceConstantReference,
    SourceExpression,
    SourceGroup,
    SourceLiteral,
    SourceMemberCall,
    SourceMemberProperty,
    SourceName,
    SourceUnary,
    SourceVariableReference,
)
from ...syntax.spans import qualified_segment_spans
from .reporting import node_span
from .state import BindContext


def root_fixes(
    context: BindContext, name: str, span: SourceSpan | None, *kinds: NativeKind
) -> tuple[SourceFix, ...]:
    """Respell a wrong-case namespace root, and the whole name when its tail resolves."""

    root = None if context.catalog is None else context.catalog.root_case_variant(name)
    segments = qualified_segment_spans(name, span)
    if root is None or segments[0] is None:
        return ()
    exact = context.catalog.case_rewrite(name, *kinds)
    whole = join_segment_spans(segments[0], segments[-1])
    if exact is not None and whole is not None and exact[len(root) :] != name[len(root) :]:
        return (SourceFix(f"Change '{name}' to '{exact}'", whole, exact),)
    return (SourceFix(f"Change '{name.split('.', 1)[0]}' to '{root}'", segments[0], root),)


def member_rewrites(
    forms: tuple[MemberForm, ...], arguments: tuple[SourceExpression, ...]
) -> tuple[str, ...]:
    """Distinct member spellings of a flat call whose argument count fits each form."""

    return tuple(
        dict.fromkeys(
            text
            for form in forms
            if len(form.arguments) + 1 == len(arguments)
            and (text := _member_rewrite(form, arguments)) is not None
        )
    )


def member_fixes(
    context: BindContext, node: SourceCall | SourceAction, kind: Literal["action", "expression"]
) -> tuple[SourceFix, ...]:
    """Rewrite a rejected card-first flat call as its member form, over the whole call.

    These are the precise spellings ``retired_hint`` offers; an action keeps its
    semicolon, and an action with a block (which member actions cannot take) gets none.
    """

    name = node.name or ""
    span = node_span(node)
    if (
        span is None
        or not node.arguments
        or (isinstance(node, SourceAction) and (node.has_block or node.children))
        or context.catalog.retired_names(name, kind)
        or context.catalog.root_case_variant(name) is not None
    ):
        return ()
    forms = context.catalog.retired_member_forms(name, kind)
    suffix = ";" if isinstance(node, SourceAction) else ""
    return tuple(
        SourceFix(f"Write '{text}'", span, text + suffix)
        for text in member_rewrites(forms, node.arguments)
    )


def _member_rewrite(form: MemberForm, arguments: tuple[SourceExpression, ...]) -> str | None:
    """Rewrite ``Flat.Name(receiver, rest...)`` as ``receiver.Member(rest...)`` from its AST."""

    receiver = _source_text(arguments[0])
    rest = [_source_text(item) for item in arguments[1:]]
    if receiver is None or any(item is None for item in rest):
        return None
    if not isinstance(
        arguments[0],
        (
            SourceName,
            SourceVariableReference,
            SourceConstantReference,
            SourceMemberProperty,
            SourceMemberCall,
            SourceCall,
            SourceGroup,
            SourceCardConversion,
        ),
    ):
        receiver = f"({receiver})"
    if form.target.kind == "expression" and not form.arguments:
        return f"{receiver}.{form.name}"
    return f"{receiver}.{form.name}({', '.join(cast(list[str], rest))})"


def _source_text(node: SourceExpression) -> str | None:
    """Render a Source AST expression back to source (explicit groups are preserved)."""

    if isinstance(node, SourceLiteral):
        value = node.value
        if isinstance(value, FloatBitsLiteral):
            return f"float_bits(0x{value.bits:08x})"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=True)
        if isinstance(value, float):
            return repr(value) if math.isfinite(value) else None
        return None if value is None else str(value)
    if isinstance(node, SourceName):
        return node.name
    if isinstance(node, SourceVariableReference):
        return f"variable({json.dumps(node.name, ensure_ascii=True)})"
    if isinstance(node, SourceConstantReference):
        return f"const({json.dumps(node.name, ensure_ascii=True)})"
    if isinstance(node, SourceGroup):
        inner = _source_text(node.expression)
        return None if inner is None else f"({inner})"
    if isinstance(node, SourceCardConversion):
        inner = _source_text(node.operand)
        return None if inner is None else f"Card({inner})"
    if isinstance(node, SourceUnary):
        inner = _source_text(node.operand)
        return None if inner is None else f"{node.operator}{inner}"
    if isinstance(node, SourceBinary):
        left, right = _source_text(node.left), _source_text(node.right)
        return None if left is None or right is None else f"{left} {node.operator} {right}"
    if isinstance(node, SourceMemberProperty):
        receiver = _source_text(node.receiver)
        return None if receiver is None else f"{receiver}.{node.member}"
    if isinstance(node, (SourceCall, SourceMemberCall)):
        arguments = [_source_text(item) for item in node.arguments]
        if any(item is None for item in arguments):
            return None
        if isinstance(node, SourceMemberCall):
            receiver = _source_text(node.receiver)
            if receiver is None:
                return None
            prefix = f"{receiver}.{node.member}"
        else:
            prefix = node.name
        return f"{prefix}({', '.join(cast(list[str], arguments))})"
    return None


_NEGATABLE = (
    SourceLiteral,
    SourceName,
    SourceCall,
    SourceMemberCall,
    SourceMemberProperty,
    SourceGroup,
    SourceVariableReference,
    SourceConstantReference,
)


def while_fixes(node: SourceAction) -> tuple[SourceFix, ...]:
    """Rewrite the header of ``while (c) {`` as ``loop { break if !(c);``, keeping the body."""

    if (
        node.name != "while"
        or len(node.arguments) != 1
        or node.block_span is None
        or (span := node_span(node)) is None
        or (condition := _source_text(node.arguments[0])) is None
    ):
        return ()
    if not isinstance(node.arguments[0], _NEGATABLE):
        condition = f"({condition})"
    block = node.block_span
    first = node_span(node.children[0]) if node.children else None
    separator = (
        "\n" + " " * (first.start_column - 1)
        if first is not None and first.start_line > block.start_line
        else " "
    )
    header = SourceSpan(
        span.filename, span.start_line, span.start_column, block.start_line, block.start_column
    )
    rewrite = f"loop {{{separator}break if !{condition};"
    return (SourceFix(f"Write 'loop {{ break if !{condition}; ... }}'", header, rewrite),)


def card_fixes(node: SourceExpression) -> tuple[SourceFix, ...]:
    span, text = node_span(node), _source_text(node)
    if span is None or text is None:
        return ()
    return (SourceFix(f"Write Card({text})", span, f"Card({text})"),)


def join_segment_spans(first: SourceSpan | None, last: SourceSpan | None) -> SourceSpan | None:
    if first is None or last is None:
        return None
    return replace(first, end_line=last.end_line, end_column=last.end_column)


def receiver_text(receiver: SourceExpression | None) -> str:
    if isinstance(receiver, SourceName):
        return receiver.name
    if isinstance(receiver, SourceVariableReference):
        return f'variable("{receiver.name}")'
    if isinstance(receiver, SourceConstantReference):
        return f'const("{receiver.name}")'
    if isinstance(receiver, SourceMemberProperty):
        return f"{receiver_text(receiver.receiver)}.{receiver.member}"
    return "<card>"
