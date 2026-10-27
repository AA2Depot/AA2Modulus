"""Semantic tokens from binder selections, authored declaration names and the lexical scan.

A name token says what a name *is*: the binder's selected target for a use, or
the declaration kind for an authored declaration name. Qualified built-in names
split at their dots into ``namespace`` tokens and one token for the last
segment. The lexical scan adds keywords, types, operators, attributes, numbers,
strings and comments wherever no name token overlaps them. Unresolved names get
no token.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from lsprotocol import types

from ...core.locations import SourceSpan
from ...hir.symbols import BoundReference
from ...language.values import SourceValue
from ...model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ...syntax import ast
from ...syntax.scanner import LexicalToken, scan_lexical
from ...syntax.walk import walk_ast
from ..protocol.positions import position_codec
from ..workspace.documents import Snapshot
from .lookup import bound_references, declaration_span

TOKEN_TYPES = (
    "namespace",
    "function",
    "method",
    "property",
    "enumMember",
    "event",
    "variable",
    "parameter",
    "macro",
    "class",
    "keyword",
    "type",
    "number",
    "string",
    "comment",
    "operator",
    "decorator",
)
TOKEN_MODIFIERS = ("declaration", "readonly", "defaultLibrary", "modification")
LEGEND = types.SemanticTokensLegend(
    token_types=list(TOKEN_TYPES), token_modifiers=list(TOKEN_MODIFIERS)
)

_TYPES = {name: index for index, name in enumerate(TOKEN_TYPES)}
_MODIFIERS = {name: 1 << index for index, name in enumerate(TOKEN_MODIFIERS)}
_LEXICAL_TYPES = {
    "keyword": "keyword",
    "type": "type",
    "operator": "operator",
    "attribute": "decorator",
    "attributeCode": "enumMember",
    "number": "number",
    "string": "string",
    "comment": "comment",
}


@dataclass(frozen=True, slots=True)
class _Token:
    start: int
    end: int
    type: str
    modifiers: tuple[str, ...] = ()


def _declaration_kind(node: object) -> tuple[str, tuple[str, ...]] | None:
    if isinstance(node, (ast.SourceGlobal, ast.SourceLocal)):
        return "variable", ()
    if isinstance(node, ast.SourceParameter):
        return "parameter", ()
    if isinstance(node, ast.SourceConstant):
        return "variable", ("readonly",)
    if isinstance(node, ast.SourceMacro):
        return "macro", ()
    if isinstance(node, ast.SourceTriggerTemplate):
        return "class", ()
    return None


def _builtin_kind(
    reference: BoundReference, protected: frozenset[str]
) -> tuple[str, tuple[str, ...]] | None:
    metadata = reference.metadata
    form = reference.member_form
    if isinstance(metadata, EventMetadata):
        return "event", ("defaultLibrary",)
    if isinstance(metadata, (NamedConstantMetadata, SourceValue)):
        return "enumMember", ("defaultLibrary", "readonly")
    if isinstance(metadata, ActionMetadata):
        return ("method" if form is not None else "function"), ("defaultLibrary",)
    if isinstance(metadata, ExpressionMetadata):
        if form is not None:
            return ("method" if form.arguments else "property"), ("defaultLibrary",)
        if reference.name.casefold() in protected:
            return "variable", ("defaultLibrary", "readonly")
        if not metadata.parameter_types:
            return "property", ("defaultLibrary", "readonly")
        return "function", ("defaultLibrary",)
    return None


def _reference_kind(
    reference: BoundReference, protected: frozenset[str], writes: frozenset[SourceSpan]
) -> tuple[str, tuple[str, ...]] | None:
    if reference.metadata is not None:
        return _builtin_kind(reference, protected)
    kind = (
        _declaration_kind(reference.declaration)
        if reference.declaration is not None
        else ("variable", ())
        if reference.type is not None
        else None
    )
    if kind is not None and reference.source_span in writes:
        return kind[0], (*kind[1], "modification")
    return kind


def _split(text: str, start: int, end: int, kind: str, modifiers: tuple[str, ...]) -> list[_Token]:
    """A qualified built-in name as namespace segments and one final-segment token."""

    segment = text[start:end]
    if "." not in segment:
        return [_Token(start, end, kind, modifiers)]
    tokens = []
    offset = start
    *qualifiers, last = segment.split(".")
    for part in qualifiers:
        tokens.append(_Token(offset, offset + len(part), "namespace", ("defaultLibrary",)))
        offset += len(part) + 1
    tokens.append(_Token(offset, offset + len(last), kind, modifiers))
    return tokens


def collect_tokens(snapshot: Snapshot) -> list[_Token]:
    """Non-overlapping tokens for the document, ordered by start offset."""

    document = snapshot.document
    codec = position_codec(document.text)
    protected = snapshot.analysis.context.catalog.protected_names
    candidates: list[_Token] = []
    writes: set[SourceSpan] = set()
    for node in walk_ast(snapshot.analysis.ast or snapshot.authoring.ast):
        if isinstance(node, (ast.SourceAssignment, ast.SourceFor)) and node.target_span:
            writes.add(node.target_span)
        kind = _declaration_kind(node)
        span = declaration_span(node)
        if kind is not None and span is not None and span.filename == document.filename:
            start, end = codec.offsets(span)
            candidates.append(_Token(start, end, kind[0], (*kind[1], "declaration")))
    frozen_writes = frozenset(writes)
    for reference in bound_references(snapshot):
        span = reference.source_span
        if span is None or span.filename != document.filename:
            continue
        kind = _reference_kind(reference, protected, frozen_writes)
        if kind is None:
            continue
        start, end = codec.offsets(span)
        if reference.metadata is not None and document.text[start:end] == reference.name:
            candidates.extend(_split(document.text, start, end, *kind))
        else:
            candidates.append(_Token(start, end, *kind))
    # Declarations come first, so they win over a use recorded at the same name;
    # expansions of one macro or template body repeat the same spans.
    ordered = sorted(enumerate(candidates), key=lambda item: (item[1].start, item[0]))
    tokens: list[_Token] = []
    for _, token in ordered:
        if token.end > token.start and (not tokens or token.start >= tokens[-1].end):
            tokens.append(token)
    return _merge(tokens, scan_lexical(document.text))


def _merge(names: list[_Token], lexical: tuple[LexicalToken, ...]) -> list[_Token]:
    """The name tokens plus every lexical token that overlaps none of them."""

    starts = [token.start for token in names]
    merged = list(names)
    for token in lexical:
        index = bisect_right(starts, token.start)
        if index and names[index - 1].end > token.start:
            continue
        if index < len(names) and names[index].start < token.end:
            continue
        merged.append(_Token(token.start, token.end, _LEXICAL_TYPES[token.category]))
    return sorted(merged, key=lambda token: token.start)


def semantic_tokens(snapshot: Snapshot, encoding: str) -> types.SemanticTokens:
    codec = position_codec(snapshot.document.text, encoding=encoding)
    data: list[int] = []
    line = character = 0
    for token in collect_tokens(snapshot):
        start = codec.position(token.start)
        end = codec.position(token.end)
        if start.line != end.line:
            continue
        data.extend(
            (
                start.line - line,
                start.character - (character if start.line == line else 0),
                end.character - start.character,
                _TYPES[token.type],
                sum(_MODIFIERS[name] for name in token.modifiers),
            )
        )
        line, character = start.line, start.character
    return types.SemanticTokens(data=data)
