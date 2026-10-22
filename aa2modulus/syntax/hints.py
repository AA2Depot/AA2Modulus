"""Help and exact fixes for common mistakes carried over from other languages.

Syntax hints inspect a failed parse: the offending token, the text around it,
and whether the failed parser state would accept a corrected token instead.
``FOREIGN_KEYWORD_HELP`` is shared with the binder, which reports constructs
such as ``while (c) { ... }`` that parse as calls of an unknown name.
"""

from __future__ import annotations

import re
from copy import copy

from lark import Token
from lark.exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken
from lark.parsers.lalr_parser_state import ParserState

from ..core.diagnostics import SourceFix
from ..core.locations import SourceSpan, line_column

_MACRO_HELP = "aa2m has no functions; define a `macro` and call it as a statement"
_ELSE_IF_HELP = "write `else if condition { ... }`"
FOREIGN_KEYWORD_HELP: dict[str, str] = {
    "while": "aa2m has no `while`; write `loop { break if !(condition); ... }`",
    "return": "aa2m has no `return`; put the statements that should not run in an `if`",
    "function": _MACRO_HELP,
    "def": _MACRO_HELP,
    "fn": _MACRO_HELP,
    "switch": "aa2m has no `switch`; use `if`, `else if` and `else`",
    "elif": _ELSE_IF_HELP,
    "elseif": _ELSE_IF_HELP,
    "elsif": _ELSE_IF_HELP,
}
"""Help for words of other languages that aa2m does not reserve."""
UNCLOSED_COMMENT_HELP = "this `/*` comment is never closed with `*/`"

_WORD_OPERATORS = {"and": "&&", "or": "||"}
_OPERAND_END = re.compile(r'[A-Za-z0-9_)\]"]\s*\Z')
_STATEMENT_WORD = re.compile(r"(?:\A|[;{}])\s*(" + "|".join(FOREIGN_KEYWORD_HELP) + r")\s*\Z")
_STATEMENT_TARGET = re.compile(r"(?:\A|[;{}])\s*([A-Za-z_][A-Za-z0-9_]*)\s*\Z")
_NOT_PREFIX = re.compile(r"(?<![A-Za-z0-9_.])not[ \t]+\Z")
_SIMPLE_OPERAND = re.compile(r'[A-Za-z0-9_.]+|"(?:[^"\\\r\n]|\\.)*"')
_COMPOUND = ("+=", "-=", "*=", "/=", "++", "--")

type Hint = tuple[str | None, tuple[SourceFix, ...]]


def _span(source: str, filename: str, start: int, end: int) -> SourceSpan:
    """The span of ``source[start:end]`` (``end`` exclusive, at least one character)."""

    end = max(end, start + 1)
    start_line, start_column = line_column(source, start)
    end_line, end_column = line_column(source, end - 1)
    return SourceSpan(filename, start_line, start_column, end_line, end_column)


def _accepts(error: UnexpectedInput, kind: str, text: str) -> bool:
    """Whether the failed parser state would shift ``text`` as ``kind`` instead."""

    state = getattr(error, "state", None)
    if not isinstance(state, ParserState):
        return False
    conf = copy(state.parse_conf)
    conf.callbacks = {}
    probe = ParserState(conf, state.lexer, list(state.state_stack), [])
    try:
        probe.feed_token(Token(kind, text))
    except UnexpectedToken:
        return False
    return True


def _statement_end(source: str, start: int) -> int | None:
    """Offset of the `;` ending the statement at ``start``, outside strings and groups."""

    depth = 0
    index = start
    while index < len(source):
        character = source[index]
        if character == '"':
            index += 1
            while index < len(source) and source[index] not in '"\n':
                index += 2 if source[index] == "\\" else 1
            if index >= len(source) or source[index] != '"':
                return None
        elif character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character in "{}" or depth < 0:
            return None
        elif character == ";" and depth == 0:
            return index
        index += 1
    return None


def _compound_hint(source: str, filename: str, position: int) -> Hint | None:
    operator = source[position : position + 2]
    target = _STATEMENT_TARGET.search(source, 0, position)
    if operator not in _COMPOUND or target is None:
        return None
    name = target.group(1)
    if operator in ("++", "--"):
        rewrite = f"{name} = {name} {operator[0]} 1"
        span = _span(source, filename, target.start(1), position + 2)
        return f"aa2m has no `{operator}`; write `{rewrite};`", (
            SourceFix(f"Write '{rewrite}'", span, rewrite),
        )
    help = f"aa2m has no `{operator}`; write `{name} = {name} {operator[0]} ...;`"
    end = _statement_end(source, position + 2)
    operand = None if end is None else source[position + 2 : end].strip()
    if end is None or not operand:
        return help, ()
    if _SIMPLE_OPERAND.fullmatch(operand) is None:
        operand = f"({operand})"
    rewrite = f"{name} = {name} {operator[0]} {operand}"
    span = _span(source, filename, target.start(1), len(source[:end].rstrip()))
    return help, (SourceFix(f"Write '{rewrite}'", span, rewrite),)


def _quote_hint(source: str, filename: str, position: int) -> Hint:
    help = 'strings use double quotes: "text"'
    close = source.find("'", position + 1)
    newline = source.find("\n", position + 1)
    if close < 0 or 0 <= newline < close:
        return help, ()
    content = source[position + 1 : close]
    if '"' in content or "\\" in content:
        return help, ()
    span = _span(source, filename, position, close + 1)
    return help, (SourceFix(f'Write "{content}"', span, f'"{content}"'),)


def syntax_hint(error: UnexpectedInput, source: str, filename: str) -> Hint:
    """Help and fixes for the fault ``error`` reports, or ``(None, ())``."""

    if isinstance(error, UnexpectedCharacters):
        position = error.pos_in_stream
        if position is not None and error.char == "'":
            return _quote_hint(source, filename, position)
        return None, ()
    token = getattr(error, "token", None)
    if not isinstance(token, Token) or token.type == "$END" or token.start_pos is None:
        return None, ()
    position = token.start_pos
    text = str(token)
    end = position + len(text)
    if text == "=" and _accepts(error, "EQUALITY_OP", "=="):
        span = _span(source, filename, position, end)
        return "use `==` to compare; `=` only assigns", (SourceFix("Use '=='", span, "=="),)
    if text == "=" and _accepts(error, "COLON", ":"):
        return "declarations need a type after the name, as in `let x: int = 1;`", ()
    # The failed state may already have reduced the left operand for a following
    # expression, so a word operator after an operand is recognized from the text.
    if text in _WORD_OPERATORS and _OPERAND_END.search(source, 0, position):
        replacement = _WORD_OPERATORS[text]
        span = _span(source, filename, position, end)
        return f"use `{replacement}`", (SourceFix(f"Use '{replacement}'", span, replacement),)
    if text == "/" and source.startswith("/*", position):
        return UNCLOSED_COMMENT_HELP, ()
    if text in ("+", "-", "*", "/"):
        compound = _compound_hint(source, filename, position)
        if compound is not None:
            return compound
    # `!` binds tighter than `not` does elsewhere, so no fix: `not a == b` is `!(a == b)`.
    if _NOT_PREFIX.search(source, 0, position) is not None:
        return "use `!` for negation, as in `!(condition)`", ()
    word = _STATEMENT_WORD.search(source, 0, position)
    if word is not None:
        keyword = word.group(1)
        fixes: tuple[SourceFix, ...] = ()
        if FOREIGN_KEYWORD_HELP[keyword] is _ELSE_IF_HELP and source[
            : word.start(1)
        ].rstrip().endswith("}"):
            span = _span(source, filename, word.start(1), word.end(1))
            fixes = (SourceFix("Use 'else if'", span, "else if"),)
        return FOREIGN_KEYWORD_HELP[keyword], fixes
    return None, ()
