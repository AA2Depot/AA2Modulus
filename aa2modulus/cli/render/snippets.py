"""Source snippets: display cells, clipped snippet lines and gutter blocks."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ...core.locations import SourceSpan
from .terminal import BLUE, BOLD, RenderOptions, paint

TAB_WIDTH = 4
# Display columns of source text shown per snippet line before clipping.
SNIPPET_WIDTH = 100
# Display columns kept before the span when a long line is clipped.
SNIPPET_LEAD = 20


class SourceTexts:
    """Source text for snippets: supplied texts first, then the disk, else none."""

    def __init__(self, texts: Mapping[str, str] | None = None) -> None:
        self._lines: dict[str, list[str] | None] = {}
        for name, text in (texts or {}).items():
            self._lines[name] = _split_lines(text)

    def lines(self, filename: str) -> list[str] | None:
        if filename not in self._lines:
            self._lines[filename] = _read_lines(filename)
        return self._lines[filename]


def _split_lines(text: str) -> list[str]:
    # Only LF advances the line number in the parser, so split on LF alone.
    return [line.removesuffix("\r") for line in text.split("\n")]


def _read_lines(filename: str) -> list[str] | None:
    if filename.startswith("<"):
        return None
    try:
        path = Path(filename)
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            return None
        return _split_lines(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def _char_width(char: str) -> int:
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def _cells(line: str) -> tuple[list[str], list[int]]:
    """Display text per code point and the display column where each starts."""

    texts: list[str] = []
    columns: list[int] = []
    column = 0
    for char in line:
        if char == "\t":
            text = " " * (TAB_WIDTH - column % TAB_WIDTH)
        elif not char.isprintable():
            text = "?"
        else:
            text = char
        texts.append(text)
        columns.append(column)
        column += sum(_char_width(item) for item in text)
    columns.append(column)
    return texts, columns


def snippet_lines(line: str, start_column: int, end_column: int | None) -> tuple[str, str]:
    """Return the displayed source line and the caret line (without gutters).

    Columns are one-based code points and ``end_column`` is inclusive; a missing
    or earlier end gives a single caret. Tabs expand, wide characters count as
    two columns, and a line wider than ``SNIPPET_WIDTH`` is clipped around the
    span with ``...`` marks.
    """

    texts, columns = _cells(line)
    start = min(max(start_column - 1, 0), len(texts))
    stop = start + 1 if end_column is None else max(end_column, start + 1)
    stop = min(stop, max(len(texts), start + 1))
    span_start = columns[start] if start < len(columns) else columns[-1]
    span_stop = columns[stop] if stop < len(columns) else columns[-1] + max(stop - len(texts), 1)
    if span_stop <= span_start:
        span_stop = span_start + 1

    first = 0
    if columns[-1] > SNIPPET_WIDTH:
        wanted = span_start - SNIPPET_LEAD
        while first < len(texts) and columns[first] < wanted:
            first += 1
        if first < 3:
            first = 0
    limit = (columns[first] if first < len(columns) else columns[-1]) + SNIPPET_WIDTH
    last = first
    while last < len(texts) and columns[last + 1] <= limit:
        last += 1
    lead = "..." if first else ""
    trail = "..." if last < len(texts) else ""
    base = columns[first] if first < len(columns) else columns[-1]
    offset = len(lead) + span_start - base
    visible_stop = min(span_stop, columns[last] if last < len(columns) else columns[-1])
    width = max(visible_stop - span_start, 1)
    shown = lead + "".join(texts[first:last]) + trail
    return shown, " " * offset + "^" * width


@dataclass(slots=True)
class SnippetBlock:
    lines: list[str] = field(default_factory=list)
    has_snippet: bool = False


def snippet_block(
    span: SourceSpan,
    sources: SourceTexts,
    width: int,
    options: RenderOptions,
    style: str,
) -> SnippetBlock:
    block = SnippetBlock()
    arrow = paint("-->", options.color, BOLD, BLUE)
    block.lines.append(
        f"{' ' * width}{arrow} {span.filename}:{span.start_line}:{span.start_column}"
    )
    lines = sources.lines(span.filename)
    if lines is None or span.start_line > len(lines):
        return block
    text = lines[span.start_line - 1]
    end_column = span.end_column
    if span.end_line is not None and span.end_line != span.start_line:
        # Underline to the end of the first line of a multi-line span.
        end_column = len(text)
    shown, carets = snippet_lines(text, span.start_column, end_column)
    bar = paint("|", options.color, BOLD, BLUE)
    number = paint(f"{span.start_line:>{width}}", options.color, BOLD, BLUE)
    block.lines.append(f"{' ' * (width + 1)}{bar}")
    block.lines.append(f"{number} {bar} {shown}".rstrip())
    marks = carets.lstrip(" ")
    indent = carets[: len(carets) - len(marks)]
    block.lines.append(
        f"{' ' * (width + 1)}{bar} {indent}{paint(marks, options.color, BOLD, style)}"
    )
    block.has_snippet = True
    return block
