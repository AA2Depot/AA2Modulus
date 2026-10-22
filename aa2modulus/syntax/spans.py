"""Source spans of the segments of a qualified name token."""

from __future__ import annotations

from dataclasses import replace

from ..core.locations import SourceSpan


def qualified_segment_spans(name: str, span: SourceSpan | None) -> tuple[SourceSpan | None, ...]:
    """Locate each segment of a lexed QUALIFIED_NAME token within its own span.

    The lexer admits no whitespace, comments or newlines inside the token, so
    segment columns follow from the token start. Inclusive end columns match the
    parser's token spans. Programmatic ASTs without spans yield no locations.
    """

    parts = name.split(".")
    if span is None:
        return (None,) * len(parts)
    result: list[SourceSpan | None] = []
    column = span.start_column
    for part in parts:
        result.append(
            replace(
                span,
                start_column=column,
                end_line=span.start_line,
                end_column=column + len(part) - 1,
            )
        )
        column += len(part) + 1
    return tuple(result)
