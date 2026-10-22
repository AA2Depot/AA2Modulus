"""Source spans of Lark tree metadata and tokens."""

from __future__ import annotations

from lark import Token
from lark.tree import Meta

from ...core.locations import SourceSpan


def meta_span(meta: Meta, filename: str) -> SourceSpan:
    return SourceSpan(
        filename,
        getattr(meta, "line", 1),
        getattr(meta, "column", 1),
        getattr(meta, "end_line", None),
        max(1, getattr(meta, "end_column", 2) - 1),
    )


def token_span(token: Token, filename: str) -> SourceSpan:
    line = token.line or 1
    column = token.column or 1
    return SourceSpan(
        filename,
        line,
        column,
        token.end_line or line,
        max(1, (token.end_column or column + 1) - 1),
    )
