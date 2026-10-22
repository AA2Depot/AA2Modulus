"""Conversions between Python source offsets, parser spans, and LSP positions."""

from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache

from lsprotocol.types import Position, Range

from ...core.locations import SourceSpan

_ENCODINGS = {"utf-8", "utf-16", "utf-32"}


class PositionCodec:
    """Convert Python string offsets and inclusive source spans to LSP positions.

    LSP positions use negotiated code units and recognize CRLF, LF, and lone CR
    as line endings. SourceSpan columns follow Lark's LF-only line counting and
    are one-based, inclusive Unicode codepoint columns.
    """

    def __init__(self, text: str, *, encoding: str = "utf-16") -> None:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not isinstance(encoding, str):
            raise TypeError("encoding must be a string")
        normalized = encoding.lower().replace("_", "-")
        if normalized not in _ENCODINGS:
            raise ValueError("encoding must be utf-8, utf-16, or utf-32")
        self.text = text
        self.encoding = normalized
        self._lines = _protocol_lines(text)
        self._line_starts = tuple(start for start, _ in self._lines)
        self._parser_line_starts = (
            0,
            *(index + 1 for index, char in enumerate(text) if char == "\n"),
        )

    def position(self, offset: int) -> Position:
        """Return the LSP position at a clamped Python codepoint offset."""

        _require_int(offset, "offset")
        offset = min(max(offset, 0), len(self.text))
        line_index = bisect_right(self._line_starts, offset) - 1
        line_index = max(line_index, 0)
        start, end = self._lines[line_index]
        offset = min(offset, end)
        units = self._units(self.text[start:offset])
        return Position(line=line_index, character=units)

    def offset(self, position: Position) -> int:
        """Return a Python offset, clamping invalid lines and columns safely.

        A character count that lands inside a UTF-8 sequence or UTF-16 surrogate
        pair is rounded down to the beginning of that Unicode codepoint.
        """

        if not isinstance(position, Position):
            raise TypeError("position must be an lsprotocol Position")
        _require_int(position.line, "position.line")
        _require_int(position.character, "position.character")
        if position.line >= len(self._lines):
            return len(self.text)
        line_index = min(max(position.line, 0), len(self._lines) - 1)
        start, end = self._lines[line_index]
        remaining = max(position.character, 0)
        for index in range(start, end):
            width = self._units(self.text[index])
            if remaining < width:
                return index
            remaining -= width
        return end

    def range(self, span: SourceSpan) -> Range:
        """Convert an inclusive, one-based parser span to an LSP half-open range."""

        start, end = self.offsets(span)
        return Range(start=self.position(start), end=self.position(end))

    def offsets(self, span: SourceSpan) -> tuple[int, int]:
        """Return the half-open Python codepoint offsets of an inclusive parser span."""

        if not isinstance(span, SourceSpan):
            raise TypeError("span must be a SourceSpan")
        start = self.parser_offset(span.start_line, span.start_column)
        end_line = span.end_line if span.end_line is not None else span.start_line
        if span.end_column is None:
            end = min(start + 1, len(self.text))
        else:
            inclusive_end = self.parser_offset(end_line, span.end_column)
            end = min(inclusive_end + 1, len(self.text))
        return start, max(start, end)

    def parser_offset(self, line: int, column: int) -> int:
        """Map parser coordinates, where only LF advances the line number."""

        if line > len(self._parser_line_starts):
            return len(self.text)
        line_index = min(max(line - 1, 0), len(self._parser_line_starts) - 1)
        start = self._parser_line_starts[line_index]
        end = self.text.find("\n", start)
        if end < 0:
            end = len(self.text)
        codepoint_offset = min(max(column - 1, 0), end - start)
        return start + codepoint_offset

    def _units(self, value: str) -> int:
        if self.encoding == "utf-32":
            return len(value)
        if self.encoding == "utf-16":
            return len(value.encode("utf-16-le", errors="surrogatepass")) // 2
        return len(value.encode("utf-8", errors="surrogatepass"))


@lru_cache(maxsize=32)
def position_codec(text: str, *, encoding: str = "utf-16") -> PositionCodec:
    """A shared codec for ``text``; requests and diagnostics reuse one per text and encoding."""

    return PositionCodec(text, encoding=encoding)


def _protocol_lines(text: str) -> tuple[tuple[int, int], ...]:
    """Return (start, content-end) offsets, excluding recognized line endings."""

    lines: list[tuple[int, int]] = []
    start = index = 0
    while index < len(text):
        char = text[index]
        if char == "\r" or char == "\n":
            lines.append((start, index))
            if char == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
                index += 1
            start = index + 1
        index += 1
    lines.append((start, len(text)))
    return tuple(lines)


def _require_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
