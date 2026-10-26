"""Completion entry point: one helper per branch of the request."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from lark.exceptions import UnexpectedInput
from lsprotocol import types

from ...context.limits import SourceLimitError
from ...context.operation import SourceContext
from ...language.types import CARD, wire_type
from ...model.types import ValueType
from ...pipeline.analysis import SourceAnalysis
from ...pipeline.authoring import SourceAuthoring
from ...syntax.ast import (
    SourceConstant,
    SourceGlobal,
    SourceLocal,
    SourceMacro,
    SourceParameter,
    SourceUnit,
)
from ...syntax.limits import check_source_text
from ...syntax.parser.errors import SourceParseError
from .call_site import call_exhausted, expected_role_at, expected_type_at
from .items import (
    CONST_STRING,
    allow_codes_listed,
    allow_completions,
    authored_items,
    builtin_items,
    constant_string_completions,
    keyword_items,
)
from .members import member_completions, member_end, member_site
from .request import CompletionRequest, CompletionSite
from .scope import visible_declarations
from .snippets import snippet_items, unavailable_keywords
from .tokens import (
    NAME_TOKENS,
    Prefix,
    build_prefix,
    classify_following,
    positions,
)

_Declaration = SourceGlobal | SourceLocal | SourceParameter | SourceConstant | SourceMacro


def completions(
    source: str,
    offset: int,
    context: SourceContext,
    *,
    encoding: str = "utf-16",
    analysis: SourceAnalysis | None = None,
    authoring: SourceAuthoring | None = None,
    texts: Mapping[str, str] | None = None,
    snippet_support: bool = False,
    source_kind: Literal["module", "library"] | None = None,
) -> list[types.CompletionItem]:
    """Return syntax and visible name completions at a Python source offset.

    ``source_kind`` defaults to the kind the filename suffix implies.
    """

    offset = min(max(offset, 0), len(source)) if isinstance(offset, int) else offset
    try:
        check_source_text(source, filename=context.filename, limits=context.source_limits)
    except SourceLimitError:
        return []
    request = CompletionRequest(
        source,
        offset,
        context,
        encoding,
        analysis,
        authoring,
        texts,
        snippet_support,
        source_kind or ("library" if context.filename.endswith(".aa2mi") else "module"),
    )
    found = _constant_string_branch(request)
    if found is not None:
        return found
    prefix = build_prefix(source, offset, context, analysis=analysis)
    if prefix is None:
        return []
    listed = allow_codes_listed(prefix.tokens)
    if listed is not None:
        return allow_completions(request, prefix, listed)
    view = request.view()
    if isinstance(view.failure, SourceLimitError) or (
        isinstance(view.failure, SourceParseError) and view.ast is None
    ):
        return []
    visible = visible_declarations(view.unit, source, offset, context)
    visible_types = {item.name: wire_type(item.type) for item in visible}
    if call_exhausted(prefix.tokens, view.unit, visible_types, context):
        return []
    expected_type = expected_type_at(prefix.tokens, view.unit, visible_types, context)
    expression_position, statement_position, event_position = positions(prefix)
    end = _replacement_end(request, prefix)
    if (
        expected_type == ValueType.BOOL
        and expression_position
        and not (prefix.tokens and prefix.tokens[-1].type == "NOT_OP")
    ):
        expected_type = None
    members = _member_branch(request, prefix, view.unit, visible_types, expected_type, end)
    if members is not None:
        return members
    existing_parentheses, existing_statement_suffix, following = classify_following(
        prefix.parser, source, end
    )
    codec = request.codec
    site = CompletionSite(
        prefix,
        visible_types,
        expected_type,
        expected_role_at(prefix.tokens, view.unit, visible_types, context),
        types.Range(codec.position(prefix.start), codec.position(end)),
        expression_position,
        statement_position,
        event_position,
        existing_parentheses,
        existing_statement_suffix,
        following,
    )
    return _syntax_branch(request, site, view.unit, visible)


def _constant_string_branch(request: CompletionRequest) -> list[types.CompletionItem] | None:
    """Constant names inside ``const("...")``; None when the cursor is elsewhere."""

    if CONST_STRING.search(request.source[: request.offset]) is None:
        return None
    string_view = request.view()
    if string_view.unit is None:
        return None
    return constant_string_completions(request, string_view)


def _replacement_end(request: CompletionRequest, prefix: Prefix) -> int:
    """Offset where the replaced text ends: the cursor, or the end of the token it is in."""

    end = min(max(request.offset, 0), len(request.source))
    if prefix.suffix:
        # A cursor inside an existing token must replace its remaining suffix too.
        try:
            for index, token in enumerate(prefix.parser.lex(request.source)):
                if index + 2 > request.context.source_limits.max_nodes:
                    break
                if token.start_pos == prefix.start and token.type in NAME_TOKENS:
                    return max(end, token.end_pos or end)
                if token.start_pos is not None and token.start_pos > end:
                    break
        except UnexpectedInput:
            pass
    return end


def _member_branch(
    request: CompletionRequest,
    prefix: Prefix,
    unit: SourceUnit | None,
    visible_types: Mapping[str, int],
    expected_type: int | None,
    end: int,
) -> list[types.CompletionItem] | None:
    """Member completions after ``receiver.``; None when the cursor is not at a member site."""

    site = member_site(prefix, unit, visible_types, request.context, expected_type=expected_type)
    if site is None:
        return None
    # Only the partial member text is replaced, never the receiver.
    end = member_end(request.source, end)
    parentheses, statement_suffix, _ = classify_following(prefix.parser, request.source, end)
    return member_completions(
        site,
        request.context,
        request.codec,
        end=end,
        snippet_support=request.snippet_support,
        existing_parentheses=parentheses,
        existing_statement_suffix=statement_suffix,
    )


def _syntax_branch(
    request: CompletionRequest,
    site: CompletionSite,
    unit: SourceUnit | None,
    visible: Sequence[SourceGlobal | SourceLocal | SourceParameter | SourceConstant],
) -> list[types.CompletionItem]:
    """Keywords, built-ins and authored names accepted at the cursor."""

    excluded = unavailable_keywords(request, site, unit)
    results = keyword_items(site, excluded)
    if request.snippet_support:
        results.extend(snippet_items(request, site, excluded))
    for item in builtin_items(request, site):
        item.text_edit = types.TextEdit(site.edit_range, item.insert_text or item.label)
        results.append(item)
    results.extend(authored_items(request, site, _authored_declarations(site, unit, visible), unit))
    if any(item.sort_text for item in results):
        # Rank the rest after the role matches without reordering them.
        for item in results:
            if item.sort_text is None:
                item.sort_text = f"1{item.label}"
    return results


def _authored_declarations(
    site: CompletionSite,
    unit: SourceUnit | None,
    visible: Sequence[SourceGlobal | SourceLocal | SourceParameter | SourceConstant],
) -> Sequence[_Declaration]:
    """Declarations offered at the cursor: statement starts, or all visible names.

    A statement starts with a macro call, an assignment target or a card
    receiver such as a card formal (``c.SetVirtue(3);``).
    """

    if site.statement_position and not site.event_position:
        statement_starts = tuple(
            item
            for item in visible
            if isinstance(item, (SourceGlobal, SourceLocal))
            or (isinstance(item, SourceParameter) and item.type is CARD)
        )
        return (*unit.macros, *statement_starts) if unit is not None else statement_starts
    if site.expression_position and not site.event_position and not site.existing_parentheses:
        return visible
    return ()
