"""Completion of ``receiver.Member`` sites."""

from __future__ import annotations

from collections.abc import Mapping

from lsprotocol import types

from ...context.operation import SourceContext
from ...core.source_names import is_source_name
from ...language.documentation import builtin_description
from ...language.values import MemberForm
from ...model.types import ValueType
from ...syntax.ast import SourceUnit
from ...syntax.parser.engine import shared_parser
from ..documentation.signatures import (
    is_property,
    member_documentation,
    member_signature,
    returns_text,
)
from ..protocol.positions import PositionCodec
from .call_site import expected_type_at
from .receivers import MemberSite, member_forms, receiver
from .tokens import Prefix, contextual_tokens, positions, statement_context

_IDENT_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")


def member_end(source: str, end: int) -> int:
    while end < len(source) and source[end] in _IDENT_CHARS:
        end += 1
    return end


def member_site(
    prefix: Prefix,
    unit: SourceUnit | None,
    visible: Mapping[str, int],
    context: SourceContext,
    *,
    expected_type: int | None,
) -> MemberSite | None:
    """The receiver and partial member when the cursor follows ``receiver.``, else ``None``."""

    tokens = prefix.tokens
    parts = prefix.suffix.split(".") if prefix.suffix else [""]
    partial, path = parts[-1], parts[:-1]
    if not all(is_source_name(part, allow_qualified=False) for part in path):
        return None
    if partial and not is_source_name(partial, allow_qualified=False):
        return None
    after_dot = bool(tokens) and tokens[-1].type == "DOT"
    if not path and not after_dot:
        return None
    if after_dot and "IDENT" not in prefix.expected:
        return None
    found = receiver(tokens, path, visible, context)
    if found is None:
        return None
    start, receiver_type = found
    partial_start = prefix.start + (len(".".join(path)) + 1 if path else 0)
    if not after_dot:
        expression_position, statement_position, event_position = positions(prefix)
        if event_position or not (expression_position or statement_position):
            return None
        return MemberSite(
            statement_position,
            receiver_type,
            None if statement_position else expected_type,
            partial,
            partial_start,
        )
    before = tokens[:start]
    statement = statement_context(before)
    if before and before[-1].type == "ON":
        return None
    if not statement:
        parsed = contextual_tokens(shared_parser(), before)
        if parsed is None or "QUALIFIED_NAME" not in parsed[1]:
            return None
        expected = expected_type_at(before, unit, visible, context)
        if expected == ValueType.BOOL and before[-1:] and before[-1].type != "NOT_OP":
            expected = None
    else:
        expected = None
    return MemberSite(statement, receiver_type, expected, partial, partial_start)


def _member_snippet(
    form: MemberForm,
    *,
    statement: bool,
    snippet_support: bool,
    existing_parentheses: bool,
    existing_statement_suffix: bool,
) -> str:
    if is_property(form) or not snippet_support or existing_parentheses:
        return form.name
    placeholders = ", ".join(
        f"${{{index}:{item.name}}}" for index, item in enumerate(form.arguments, 1)
    )
    suffix = ";" if statement and not existing_statement_suffix else ""
    return f"{form.name}({placeholders}){suffix}$0"


def member_completions(
    site: MemberSite,
    context: SourceContext,
    codec: PositionCodec,
    *,
    end: int,
    snippet_support: bool,
    existing_parentheses: bool,
    existing_statement_suffix: bool,
) -> list[types.CompletionItem]:
    edit_range = types.Range(codec.position(site.partial_start), codec.position(end))
    results: list[types.CompletionItem] = []
    for form in member_forms(context, site):
        if site.partial and not form.name.casefold().startswith(site.partial.casefold()):
            continue
        target = context.catalog.member_target(form)
        body = builtin_description(context.source_policy, target)
        insert = _member_snippet(
            form,
            statement=site.statement,
            snippet_support=snippet_support,
            existing_parentheses=existing_parentheses,
            existing_statement_suffix=existing_statement_suffix,
        )
        text = member_documentation(
            form, target, body, returns=returns_text(context.source_policy, target)
        )
        results.append(
            types.CompletionItem(
                label=form.name,
                kind=types.CompletionItemKind.Property
                if is_property(form)
                else types.CompletionItemKind.Method,
                detail=member_signature(form, context.source_policy),
                filter_text=form.name,
                documentation=types.MarkupContent(types.MarkupKind.Markdown, text),
                insert_text=insert,
                insert_text_format=types.InsertTextFormat.Snippet
                if snippet_support and not existing_parentheses and not is_property(form)
                else types.InsertTextFormat.PlainText,
                text_edit=types.TextEdit(edit_range, insert),
            )
        )
    return results
