"""Leading-comment documentation for source declarations."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from textwrap import dedent

from ..protocol.positions import position_codec

# An unclosed block string runs to the end of the text, as in the lexical scanner.
_BLOCK_STRING = re.compile(r'"""(?:[^"\\]|\\[\s\S]|"(?!""))*(?:"""|\Z)')


@dataclass(frozen=True, slots=True)
class _Comment:
    start: int
    end: int
    leading: bool


@lru_cache(maxsize=8)
def _comments(source: str) -> tuple[tuple[_Comment, ...], tuple[int, ...]]:
    """Locate comments outside strings and block strings; cache only a bounded set of texts."""

    result: list[_Comment] = []
    index = 0
    code_on_line = False
    while index < len(source):
        char = source[index]
        if block := _BLOCK_STRING.match(source, index):
            code_on_line = True
            index = block.end()
        elif char == '"':
            code_on_line = True
            index += 1
            while index < len(source):
                if source[index] == "\\":
                    index += 2
                elif source[index] == '"':
                    index += 1
                    break
                else:
                    index += 1
        elif source.startswith("//", index):
            end = source.find("\n", index)
            end = len(source) if end < 0 else end
            result.append(_Comment(index, end, not code_on_line))
            index = end
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                break
            end += 2
            result.append(_Comment(index, end, not code_on_line))
            if "\n" in source[index:end] or "\r" in source[index:end]:
                code_on_line = False
            index = end
        else:
            if char in "\r\n":
                code_on_line = False
            elif not char.isspace():
                code_on_line = True
            index += 1
    return tuple(result), tuple(item.end for item in result)


def declaration_documentation(node: object, texts: Mapping[str, str] | None) -> str:
    span = getattr(node, "source_span", None)
    if span is None or texts is None or span.filename not in texts:
        return ""
    source = texts[span.filename]
    offset = position_codec(source).parser_offset(span.start_line, span.start_column)
    comments, ends = _comments(source)
    index = bisect_right(ends, offset) - 1
    end = offset
    parts: list[str] = []
    while index >= 0:
        comment = comments[index]
        gap = source[comment.end : end]
        if not comment.leading or gap.strip() or len(re.findall(r"\r\n|\r|\n", gap)) > 1:
            break
        text = source[comment.start : comment.end]
        if text.startswith("//"):
            parts.append(text[3:] if text.startswith("///") else text[2:])
        else:
            text = text[2:-2]
            parts.append("\n".join(re.sub(r"^\s*\* ?", "", line) for line in text.splitlines()))
        end = comment.start
        index -= 1
    return dedent("\n".join(reversed(parts))).strip()
