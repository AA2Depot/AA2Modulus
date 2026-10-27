"""Syntax errors: the located error type and readable messages for Lark failures."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from lark import Token
from lark.exceptions import UnexpectedInput

from ...core.diagnostics import Diagnostic, SourceFix
from ...core.locations import SourceSpan, line_column
from ..hints import syntax_hint
from .engine import shared_parser
from .spans import token_span


@dataclass(slots=True)
class SourceParseError(ValueError):
    """Stable diagnostic wrapper for unified-source syntax failures."""

    filename: str
    line: int
    column: int
    message: str
    code: str = "SYNTAX_ERROR"
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    help: str | None = field(default=None, compare=False, repr=False, kw_only=True)
    fixes: tuple[SourceFix, ...] = field(default=(), compare=False, repr=False, kw_only=True)

    def __str__(self) -> str:
        return f"{self.filename}:{self.line}:{self.column}: error[{self.code}]: {self.message}"

    def to_diagnostic(self) -> Diagnostic:
        return Diagnostic(
            self.filename,
            self.line,
            self.column,
            "error",
            self.code,
            self.message,
            source_span=self.source_span,
            help=self.help,
            fixes=self.fixes,
        )


_TERMINAL_TEXT = {
    "$END": "end of file",
    "IDENT": "a name",
    "QUALIFIED_NAME": "a name",
    "ESCAPED_STRING": "a string",
    "SIGNED_INT": "an integer",
    "SIGNED_FLOAT": "a number",
    "HEX_INT": "a hex number",
    "BOOLEAN": "`true` or `false`",
    "LOOP_KEYWORD": "`break` or `continue`",
    "STANDALONE_ELSE": "`Else`",
    "STANDALONE_ELSEIF": "`ElseIf`",
    "EQUALITY_OP": "an operator",
    "RELATIONAL_OP": "an operator",
    "ADD_OP": "an operator",
    "MUL_OP": "an operator",
    "_ALLOW": "`@allow`",
}


_EXPRESSION_STARTS = frozenset(
    {
        "ESCAPED_STRING",
        "BOOLEAN",
        "SIGNED_FLOAT",
        "SIGNED_INT",
        "NOT_OP",
        "FLOAT_BITS",
        "VARIABLE",
        "CARD",
        "RAW_EXPRESSION",
        "CONST",
        "QUALIFIED_NAME",
        "IDENT",
        "LPAR",
    }
)


_CLOSERS = frozenset({"SEMICOLON", "RPAR", "RBRACE", "RSQB"})


_MAX_EXPECTED = 5


def _terminal_text(name: str) -> str:
    text = _TERMINAL_TEXT.get(name)
    if text is not None:
        return text
    for terminal in shared_parser().terminals:
        if terminal.name == name and terminal.pattern.type == "str":
            return f"`{terminal.pattern.value}`"
    return name.lower().replace("_", " ")


def _expected_text(names: Iterable[str]) -> str | None:
    """Readable ``expected ...`` alternatives, or ``None`` when too many to be useful."""

    expected = set(names)
    if len(expected) > 1:
        # An attribute may prefix many items; naming it would crowd out the item.
        expected.discard("_ALLOW")
    texts: dict[str, int] = {}
    order = {terminal.name: index for index, terminal in enumerate(shared_parser().terminals)}
    if {"ESCAPED_STRING", "SIGNED_INT"} <= expected:
        expected -= _EXPRESSION_STARTS
        texts["an expression"] = -1
    for name in expected:
        texts.setdefault(_terminal_text(name), order.get(name, len(order)))
    ranked = sorted(texts, key=lambda text: (texts[text], text))
    if not ranked or len(ranked) > _MAX_EXPECTED:
        return None
    if len(ranked) == 1:
        return ranked[0]
    if len(ranked) == 2:
        return f"{ranked[0]} or {ranked[1]}"
    return ", ".join(ranked[:-1]) + f", or {ranked[-1]}"


def _found_text(token: Token) -> str:
    if token.type == "$END":
        return "end of file"
    text = str(token)
    return f"`{text if len(text) <= 24 else text[:21] + '...'}`"


def _end_of_previous_token(source: str, position: int) -> int:
    """Offset just after the last non-blank character before ``position``."""

    end = position
    while end > 0 and source[end - 1].isspace():
        end -= 1
    return end


def unexpected_error(error: UnexpectedInput, filename: str, source: str) -> SourceParseError:
    """A located ``expected …, found …`` error with help for a Lark syntax failure."""

    token = getattr(error, "token", None)
    position = getattr(error, "pos_in_stream", None)
    expected_names = getattr(error, "expected", None) or getattr(error, "allowed", None) or ()
    expected = _expected_text(expected_names)
    if isinstance(token, Token):
        at_end = token.type == "$END"
        if at_end and "RBRACE" in expected_names:
            expected = "`}`"
        if at_end:
            position = len(source)
        elif position is None:
            position = token.start_pos
        if expected is None:
            message = "unexpected end of file" if at_end else f"unexpected {_found_text(token)}"
        else:
            message = f"expected {expected}, found {_found_text(token)}"
        span: SourceSpan | None = None if at_end else token_span(token, filename)
        if not at_end and position is not None and set(expected_names) & _CLOSERS:
            # A missing terminator belongs after the previous token, not on the next line.
            end = _end_of_previous_token(source, position)
            if end < position and "\n" in source[end:position]:
                position = end
                span = None
    else:
        character = getattr(error, "char", None)
        if position is None:
            position = len(source)
        if character == '"' and source[position - 2 : position + 1] == '"""':
            # The lexer reads an unclosed `"""` as the empty string `""` and a `"`.
            message = 'unterminated block string; close it with `"""` on its own line'
            position -= 2
        elif character == '"':
            message = "unterminated string literal"
        else:
            shown = repr(character)[1:-1] if character else "input"
            message = f"unexpected character `{shown}`"
            if expected is not None:
                message += f", expected {expected}"
        span = None
        if isinstance(character, str) and character != '"':
            line = getattr(error, "line", None) or 1
            column = getattr(error, "column", None) or 1
            span = SourceSpan(filename, line, column, line, column)
    if span is None:
        line, column = line_column(source, min(max(position or 0, 0), len(source)))
        span = SourceSpan(filename, line, column, line, column)
    help, fixes = syntax_hint(error, source, filename)
    return SourceParseError(
        filename,
        span.start_line,
        span.start_column,
        message,
        source_span=span,
        help=help,
        fixes=fixes,
    )
