"""An error-tolerant lexical scan of source text into highlighting categories.

The scan reads the text alone, so a file with syntax errors is still fully
categorized. Its word sets come from the lexicon, and building a scanner raises
when the lexicon's groups or literal patterns no longer match its table, so a
grammar change cannot skip it. Comment tokens never cross a line: they break at
``\\r\\n``, ``\\r`` and ``\\n``, like LSP positions.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from threading import Lock

from .lexicon import Lexicon, source_lexicon

# The category of each lexicon group; ``None`` leaves the group uncategorized.
_GROUP_CATEGORIES: dict[str, str | None] = {
    "keywords": "keyword",
    "types": "type",
    "conversions": "type",
    "rawForms": "keyword",
    "rawPayload": "keyword",
    "literals": "keyword",
    "attributes": "attribute",
    "operators": "operator",
    "punctuation": None,
}
_PUNCTUATION_OPERATORS = frozenset({"="})
_IDENTIFIER = "[A-Za-z_][A-Za-z0-9_]*"
# The lexicon's number patterns without the sign, which is scanned as an operator.
_NUMBER_PATTERNS = {
    "hexInteger": "0[xX][0-9A-Fa-f]{1,8}",
    "float": r"(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[fF]?",
    "integer": "[0-9]+",
}
_SIGN = "[+-]?"
# ``invalid`` is a raw value after these words (the grammar's ``raw_value``) and a type elsewhere.
_INVALID = "invalid"
_VALUE_WORDS = frozenset({"default", "current", "constant"})
_ALLOW = "@allow"
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


@dataclass(frozen=True, slots=True)
class LexicalToken:
    """A categorized text range: ``keyword``, ``type``, ``operator``, ``attribute``,
    ``attributeCode``, ``number``, ``string`` or ``comment``.
    """

    start: int
    end: int
    category: str


class LexicalScanner:
    """Categorize words, symbols, numbers, strings and comments without a parse.

    Only an exact lexicon word gets a token, and a dotted name only when it is
    one (``import.trigger``). A word after ``.`` is a member name and gets
    none. Identifiers inside ``@allow( … )`` are ``attributeCode``. An open
    string ends at its line end and an open block comment at the end of the
    text; an unknown character is skipped.
    """

    def __init__(self, lexicon: Lexicon) -> None:
        groups = dict(lexicon.groups)
        if groups.keys() != _GROUP_CATEGORIES.keys():
            raise ValueError(f"lexicon groups {sorted(groups)!r} do not match the scanner table")
        patterns = dict(lexicon.patterns)
        expected = {
            "identifier": _IDENTIFIER,
            "qualifiedName": rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})+",
            **_NUMBER_PATTERNS,
        }
        for name, pattern in expected.items():
            if patterns.get(name, "").removeprefix(_SIGN) != pattern:
                raise ValueError(f"lexicon pattern {name!r} does not match the scanner")
        categories: dict[str, str] = {}
        symbols: list[str] = []
        word = re.compile(rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})*")
        for group, literals in groups.items():
            category = _GROUP_CATEGORIES[group]
            for literal in literals:
                if category is not None:
                    categories[literal] = category
                elif literal in _PUNCTUATION_OPERATORS:
                    categories[literal] = "operator"
                if not word.fullmatch(literal):
                    symbols.append(literal)
        if missing := sorted({_INVALID, _ALLOW, *_VALUE_WORDS} - categories.keys()):
            raise ValueError(f"scanner words missing from the lexicon {missing!r}")
        self._categories = categories
        self._pattern = re.compile(
            "|".join(
                (
                    r"(?P<space>\s+)",
                    r"(?P<comment>//[^\n]*|/\*(?:[\s\S]*?\*/|[\s\S]*))",
                    r'(?P<string>"(?:[^"\\\r\n]|\\[^\r\n]?)*"?)',
                    f"(?P<number>{'|'.join(_NUMBER_PATTERNS.values())})",
                    f"(?P<word>{word.pattern})",
                    "(?P<symbol>"
                    + "|".join(re.escape(item) for item in sorted(symbols, key=len, reverse=True))
                    + ")",
                )
            )
        )

    def scan(self, text: str) -> tuple[LexicalToken, ...]:
        tokens: list[LexicalToken] = []
        previous = ""
        in_codes = False
        offset = 0
        while offset < len(text):
            match = self._pattern.match(text, offset)
            if match is None:
                previous, in_codes = text[offset], False
                offset += 1
                continue
            start, offset = match.span()
            kind, value = match.lastgroup, match.group()
            if kind == "space":
                continue
            if kind == "comment":
                tokens.extend(_line_tokens(text, start, offset))
                continue
            category = self._category(kind, value, previous, in_codes=in_codes)
            if category is not None:
                tokens.append(LexicalToken(start, offset, category))
            in_codes = (previous == _ALLOW and value == "(") or (
                in_codes and (value == "," or category == "attributeCode")
            )
            previous = value
        return tuple(tokens)

    def _category(
        self, kind: str | None, value: str, previous: str, *, in_codes: bool
    ) -> str | None:
        if kind in ("string", "number"):
            return kind
        if kind == "symbol":
            return self._categories.get(value)
        if previous == ".":
            return None
        if value == _INVALID and previous in _VALUE_WORDS:
            return "keyword"
        if value in self._categories:
            return self._categories[value]
        if in_codes and "." not in value:
            return "attributeCode"
        return None


def _line_tokens(text: str, start: int, end: int) -> Iterator[LexicalToken]:
    """One ``comment`` token per non-empty line of ``text[start:end]``."""

    for line_break in _LINE_BREAK.finditer(text, start, end):
        if line_break.start() > start:
            yield LexicalToken(start, line_break.start(), "comment")
        start = line_break.end()
    if end > start:
        yield LexicalToken(start, end, "comment")


_scanner: LexicalScanner | None = None
_scanner_lock = Lock()


def scan_lexical(text: str) -> tuple[LexicalToken, ...]:
    """Scan ``text`` with the scanner for the package grammar, built on first use."""

    global _scanner
    scanner = _scanner
    if scanner is None:
        with _scanner_lock:
            scanner = _scanner
            if scanner is None:
                scanner = LexicalScanner(source_lexicon())
                _scanner = scanner
    return scanner.scan(text)
