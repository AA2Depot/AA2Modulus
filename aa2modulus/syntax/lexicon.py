"""The lexical surface of the source grammar as named groups, and its fingerprint.

Every literal a grammar terminal matches belongs to exactly one group of
``_GROUPS``. A grammar literal missing from the table, or a table literal the
grammar no longer has, raises, so a grammar change cannot skip the lexicon. The
fingerprint hashes only the lexicon, so built-ins, policy and the language
version never change it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from lark.lexer import TerminalDef

from ..metadata.fingerprint import canonical_hash
from .parser.engine import shared_parser

_GROUPS: dict[str, frozenset[str]] = {
    "keywords": frozenset(
        {
            "Else",
            "ElseIf",
            "break",
            "const",
            "continue",
            "current",
            "default",
            "depends_on",
            "description",
            "else",
            "for",
            "from",
            "global",
            "if",
            "import",
            "import.trigger",
            "initialized",
            "let",
            "loop",
            "macro",
            "module",
            "on",
            "param",
            "slot",
            "to",
            "trigger",
            "variable",
        }
    ),
    "types": frozenset({"bool", "card", "float", "int", "invalid", "string", "type"}),
    "conversions": frozenset({"Card"}),
    "rawForms": frozenset({"raw_action", "raw_event", "raw_expression"}),
    "rawPayload": frozenset({"constant", "named_constant", "parameters"}),
    "literals": frozenset({"false", "float_bits", "true"}),
    "attributes": frozenset({"@allow"}),
    "operators": frozenset({"!", "!=", "&&", "*", "+", "-", "/", "<", "<=", "==", ">", ">=", "||"}),
    "punctuation": frozenset({"(", ")", ",", ".", ":", ";", "=", "[", "]", "{", "}"}),
}
_PATTERNS = {
    "IDENT": "identifier",
    "QUALIFIED_NAME": "qualifiedName",
    "SIGNED_INT": "integer",
    "SIGNED_FLOAT": "float",
    "HEX_INT": "hexInteger",
}
# Strings decode with ``json.loads`` (``transform/base.py``); comments do not nest.
# Lark stores the grammar's ``\n`` escape as a newline character.
_STRING_TERMINALS = frozenset({"ESCAPED_STRING", "BLOCK_STRING"})
_COMMENT_PATTERNS = frozenset({"\\/\\/[^\n]*", r"\/\*[\s\S]*?\*\/"})

_WORD_BOUNDARY = "(?![A-Za-z0-9_])"
_LITERAL_REGEX = re.compile(r"(?:\\.|[^\\\[\](){}*+?|^$.])+")


@dataclass(frozen=True, slots=True)
class Lexicon:
    """Sorted literals per group and the authored regex of each literal form."""

    groups: tuple[tuple[str, tuple[str, ...]], ...]
    patterns: tuple[tuple[str, str], ...]

    def data(self) -> dict[str, object]:
        """The canonical JSON form that the fingerprint hashes."""

        return {
            **{name: list(literals) for name, literals in self.groups},
            "patterns": dict(self.patterns),
            "strings": "json",
            "blockStrings": {
                "delimiter": '"""',
                "contexts": ["description"],
                "lineBreak": "\r\n",
                "escapes": "json",
            },
            "comments": {"line": "//", "block": ["/*", "*/"]},
        }

    @property
    def fingerprint(self) -> str:
        return canonical_hash(self.data())


def terminal_literals(terminal: TerminalDef) -> tuple[str, ...]:
    """The exact texts a literal terminal matches; empty for a pattern terminal.

    Lark renders a terminal of string alternatives as ``(?:a|b)``, and keyword
    terminals add a word-boundary lookahead.
    """

    pattern = terminal.pattern
    if pattern.type == "str":
        return (str(pattern.value),)
    body = str(pattern.value).removesuffix(_WORD_BOUNDARY)
    if body.startswith("(?:") and body.endswith(")"):
        body = body[3:-1]
    alternatives = body.split("|")
    if not all(_LITERAL_REGEX.fullmatch(item) for item in alternatives):
        return ()
    return tuple(re.sub(r"\\(.)", r"\1", item) for item in alternatives)


def build_lexicon(terminals: Iterable[TerminalDef], *, ignored: Iterable[str]) -> Lexicon:
    """Group the literals of ``terminals``; raise when the table and grammar disagree."""

    literals: set[str] = set()
    patterns: dict[str, str] = {}
    comments: set[str] = set()
    ignored_names = frozenset(ignored)
    for terminal in terminals:
        found = terminal_literals(terminal)
        if found:
            literals.update(found)
        elif terminal.name in _PATTERNS:
            patterns[_PATTERNS[terminal.name]] = str(terminal.pattern.value)
        elif terminal.name in ignored_names:
            if terminal.name != "WS":
                comments.add(str(terminal.pattern.value))
        elif terminal.name not in _STRING_TERMINALS:
            raise ValueError(f"unclassified grammar terminal {terminal.name!r}")
    classified = frozenset[str]().union(*_GROUPS.values())
    if len(classified) != sum(len(group) for group in _GROUPS.values()):
        raise ValueError("a literal is classified in more than one group")
    if unknown := sorted(literals - classified):
        raise ValueError(f"unclassified grammar literals {unknown!r}")
    if missing := sorted(classified - literals):
        raise ValueError(f"classified literals missing from the grammar {missing!r}")
    if missing_patterns := sorted(set(_PATTERNS.values()) - patterns.keys()):
        raise ValueError(f"literal forms missing from the grammar {missing_patterns!r}")
    if comments != _COMMENT_PATTERNS:
        raise ValueError(f"unexpected comment patterns {sorted(comments)!r}")
    return Lexicon(
        tuple((name, tuple(sorted(group))) for name, group in _GROUPS.items()),
        tuple(sorted(patterns.items())),
    )


def source_lexicon() -> Lexicon:
    parser = shared_parser()
    return build_lexicon(parser.terminals, ignored=parser.parser.lexer_conf.ignore)
