"""The ``aa2m`` lexer: language words, literals and built-in names."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, ClassVar

from pygments.lexer import RegexLexer, words
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String, Whitespace

from .words import (
    ATTRIBUTES,
    CONSTANTS,
    CONVERSIONS,
    FUNCTIONS,
    KEYWORDS,
    LITERALS,
    MEMBERS,
    OPERATORS,
    PATTERNS,
    PUNCTUATION,
    RAW_FORMS,
    RAW_PAYLOAD,
    TYPES,
)

IDENTIFIER = PATTERNS["identifier"]
# Signed literals would take the minus of `x-1`; signs are left to the operator rule.
HEX, FLOAT, INTEGER = (
    PATTERNS[form].removeprefix("[+-]?") for form in ("hexInteger", "float", "integer")
)

# Later groups win, so a language word is never shown as a built-in name.
NAMED: dict[str, Any] = {
    **dict.fromkeys(FUNCTIONS, Name.Function),
    **dict.fromkeys(CONSTANTS, Name.Constant),
    **dict.fromkeys(CONVERSIONS, Name.Builtin),
    **dict.fromkeys(LITERALS, Keyword.Constant),
    **dict.fromkeys(RAW_PAYLOAD, Keyword.Pseudo),
    **dict.fromkeys(RAW_FORMS, Keyword.Reserved),
    **dict.fromkeys(TYPES, Keyword.Type),
    **dict.fromkeys(KEYWORDS, Keyword),
}


def _name_tokens(start: int, text: str) -> Iterator[tuple[int, Any, str]]:
    """Tokens of a dotted name: the longest known prefix, then each member.

    A name that starts with ``.`` is a member of the value before it, as in
    ``Card(3).FullName``.
    """

    if text in NAMED:
        yield start, NAMED[text], text
        return
    head, dot, member = text.rpartition(".")
    if not dot:
        yield start, Name, text
        return
    if head:
        yield from _name_tokens(start, head)
    yield start + len(head), Punctuation, dot
    yield start + len(head) + 1, Name.Function if member in MEMBERS else Name, member


def _names(lexer: RegexLexer, match: re.Match[str]) -> Iterator[tuple[int, Any, str]]:
    return _name_tokens(match.start(), match.group())


# Pygments ships no type information, so mypy sees its base class as Any.
class Aa2mLexer(RegexLexer):  # type: ignore[misc]
    """Highlights ``.aa2m`` source."""

    name = "aa2m"
    aliases = ("aa2m",)
    filenames = ("*.aa2m",)

    tokens: ClassVar[dict[str, list[tuple[Any, ...]]]] = {
        "root": [
            (r"\s+", Whitespace),
            (r"//.*?$", Comment.Single),
            (r"/\*[\s\S]*?\*/", Comment.Multiline),
            (r'"""[\s\S]*?"""', String.Doc),
            (r'"(?:[^"\\\n]|\\.)*"', String.Double),
            (words(sorted(ATTRIBUTES), suffix=r"\b"), Name.Decorator),
            (HEX, Number.Hex),
            (FLOAT, Number.Float),
            (INTEGER, Number.Integer),
            (rf"\.?{IDENTIFIER}(?:\.{IDENTIFIER})*", _names),
            (words(sorted(OPERATORS)), Operator),
            (words(sorted(PUNCTUATION)), Punctuation),
        ],
    }
