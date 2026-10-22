"""Bounded LALR syntax recovery shared by editor views and syntax diagnostics.

Recovery feeds production-lexer tokens to an interactive production parser,
checkpoints at completed ``{``/``}``/``;`` boundaries, rolls back to the last
checkpoint on a fault and resynchronizes at ``;``, ``}``, a declaration keyword
or a later line. Editor views use the retained tokens; ``syntax_diagnostics``
uses the recorded faults to report every independent syntax error of a file.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from copy import copy
from dataclasses import replace

from lark import Token
from lark.exceptions import UnexpectedCharacters, UnexpectedInput
from lark.lexer import TerminalDef
from lark.parsers.lalr_interactive_parser import InteractiveParser

from ..context.limits import SourceLimitError
from ..context.operation import SourceContext
from ..core.diagnostics import Diagnostic
from .hints import UNCLOSED_COMMENT_HELP
from .limits import check_source_text
from .parser.engine import shared_parser
from .parser.errors import SourceParseError, unexpected_error
from .parser.spans import token_span

MAX_FAULTS = 32
BOUNDARY_TOKENS = frozenset({"LBRACE", "RBRACE", "SEMICOLON"})
_DECLARATION_TOKENS = frozenset(
    {"LET", "GLOBAL", "ON", "MODULE", "MACRO", "TRIGGER", "IMPORT", "PARAM", "SLOT", "CONST"}
)
# Recovery work per reportable syntax error; suppressed cascades also cost a fault.
_FAULTS_PER_ERROR = 4

type _Fault = tuple[int, SourceParseError]
"""A recorded fault: its source offset and the error the parser would report there."""


def fault_limit(filename: str) -> SourceLimitError:
    return SourceLimitError(
        Diagnostic(
            filename,
            1,
            1,
            "error",
            "EDITOR_RECOVERY_LIMIT",
            f"editor recovery exceeds the limit of {MAX_FAULTS} syntax faults",
        )
    )


def _blank(source: str, start: int, end: int) -> str:
    return source[:start] + re.sub(r"[^\r\n]", " ", source[start:end]) + source[end:]


def lex_tokens(
    source: str,
    context: SourceContext,
    *,
    cursor: bool = False,
    max_faults: int = MAX_FAULTS,
    record: list[_Fault] | None = None,
) -> tuple[tuple[Token, ...], int]:
    """Use the production lexer; mask only lexically invalid fragments.

    ``record`` receives each invalid character or unterminated string.
    """

    check_source_text(source, filename=context.filename, limits=context.source_limits)
    masked = source
    faults = 0
    while True:
        tokens: list[Token] = []
        try:
            previous: Token | None = None
            for token in shared_parser().lex(masked):
                if len(tokens) + 2 > context.source_limits.max_nodes:
                    raise SourceLimitError(
                        Diagnostic(
                            context.filename,
                            token.line or 1,
                            token.column or 1,
                            "error",
                            "SOURCE_NODE_LIMIT",
                            "editor token stream exceeds the source node limit",
                        )
                    )
                # A complete block comment is ignored by the grammar. Seeing
                # its opener as adjacent operator tokens means it is unfinished.
                if (
                    previous is not None
                    and str(previous) == "/"
                    and str(token) == "*"
                    and previous.end_pos == token.start_pos
                ):
                    if cursor:
                        raise SourceParseError(
                            context.filename,
                            previous.line or 1,
                            previous.column or 1,
                            "cursor is inside an unfinished comment",
                        )
                    if record is not None:
                        record.append(
                            (
                                previous.start_pos or 0,
                                SourceParseError(
                                    context.filename,
                                    previous.line or 1,
                                    previous.column or 1,
                                    "unexpected `/`",
                                    source_span=token_span(previous, context.filename),
                                    help=UNCLOSED_COMMENT_HELP,
                                ),
                            )
                        )
                    masked = _blank(masked, previous.start_pos or 0, len(masked))
                    faults += 1
                    break
                tokens.append(token)
                previous = token
            else:
                end = tokens[-1].end_pos or 0 if tokens else 0
                if cursor and re.search(r"//[^\n]*\Z", masked[end:]):
                    raise SourceParseError(context.filename, 1, 1, "cursor is inside a comment")
                return tuple(tokens), faults
        except UnexpectedCharacters as exc:
            start = exc.pos_in_stream
            if start is None:
                raise unexpected_error(exc, context.filename, source) from exc
            if record is not None:
                record.append((start, unexpected_error(exc, context.filename, source)))
            end = start + 1
            if masked[start] == '"':
                # Unterminated strings cannot contain a following declaration
                # on the next physical line in the production grammar.
                newline = masked.find("\n", start)
                end = len(masked) if newline < 0 else newline
                if cursor and end == len(masked):
                    raise unexpected_error(exc, context.filename, source) from exc
            elif cursor and start + 1 == len(masked):
                raise unexpected_error(exc, context.filename, source) from exc
            masked = _blank(masked, start, end)
            faults += 1
        if faults > max_faults:
            raise fault_limit(context.filename)


def _machine() -> InteractiveParser:
    machine = shared_parser().parse_interactive()
    machine.parser_state.parse_conf = copy(machine.parser_state.parse_conf)
    machine.parser_state.parse_conf.callbacks = {}
    return machine


def _normalize(
    machine: InteractiveParser, token: Token, terminals: dict[str, TerminalDef]
) -> Token:
    accepted = machine.accepts()
    if token.type in accepted:
        return token
    matches = [
        terminal.name
        for name in accepted
        if (terminal := terminals.get(name)) is not None
        and terminal.pattern is not None
        and terminal.pattern.type == "str"
        and re.fullmatch(terminal.pattern.to_regexp(), str(token)) is not None
    ]
    return Token.new_borrow_pos(matches[0], str(token), token) if len(matches) == 1 else token


def retain_tokens(
    tokens: tuple[Token, ...],
    context: SourceContext,
    faults: int,
    *,
    max_faults: int = MAX_FAULTS,
    source: str = "",
    record: list[_Fault] | None = None,
) -> tuple[InteractiveParser, list[Token], InteractiveParser, int, int, bool]:
    """Feed ``tokens`` with rollback recovery.

    With ``record`` (diagnostics), skipping also passes over whole ``{ ... }``
    groups, so a block whose header failed cannot close its container. A fault
    is recorded only when a token was fed successfully since the previous fault
    (a resync token that fails again belongs to the earlier fault), and never
    at a ``}`` after an earlier fault, which is nearly always a lost ``{``.
    The last result says whether the final token fed successfully.
    """

    machine = _machine()
    terminals = {item.name: item for item in shared_parser().terminals}
    checkpoint = machine.copy(deepcopy_values=False)
    checkpoint_count = 0
    checkpoint_depth = 0
    retained: list[Token] = []
    skipping = False
    failed_line = 0
    delimiter_depth = 0
    skipped_depth = 0
    fed = True
    for raw in tokens:
        token = _normalize(machine, raw, terminals)
        if skipping and record is not None:
            if token.type == "LBRACE":
                skipped_depth += 1
                continue
            if skipped_depth:
                skipped_depth -= token.type == "RBRACE"
                continue
        if skipping:
            accepted = machine.accepts()
            may_resume = (
                token.type == "RBRACE"
                or token.type in _DECLARATION_TOKENS
                or (token.line or 1) > failed_line
            )
            if token.type == "SEMICOLON":
                skipping = False
                continue
            if not may_resume or token.type not in accepted:
                continue
        try:
            machine.feed_token(token)
        except UnexpectedInput as exc:
            if record is not None and fed and not (faults and token.type == "RBRACE"):
                record.append(
                    (token.start_pos or 0, unexpected_error(exc, context.filename, source))
                )
            faults += 1
            fed = False
            if faults > max_faults:
                raise fault_limit(context.filename) from exc
            machine = checkpoint.copy(deepcopy_values=False)
            del retained[checkpoint_count:]
            delimiter_depth = checkpoint_depth
            skipping = True
            failed_line = token.line or 1
            token = _normalize(machine, raw, terminals)
            skipped_depth = int(record is not None and token.type == "LBRACE")
            if token.type == "SEMICOLON":
                skipping = False
                continue
            if token.type not in {"RBRACE", *_DECLARATION_TOKENS}:
                continue
            try:
                machine.feed_token(token)
            except UnexpectedInput:
                machine = checkpoint.copy(deepcopy_values=False)
                continue
        skipping = False
        fed = True
        retained.append(token)
        if token.type in {"LBRACE", "LPAR", "LSQB"}:
            delimiter_depth += 1
            if delimiter_depth > context.source_limits.max_syntax_depth:
                raise SourceLimitError(
                    Diagnostic(
                        context.filename,
                        token.line or 1,
                        token.column or 1,
                        "error",
                        "SOURCE_DEPTH_LIMIT",
                        "editor syntax exceeds the source depth limit",
                    )
                )
        elif token.type in {"RBRACE", "RPAR", "RSQB"}:
            delimiter_depth -= 1
        if token.type in BOUNDARY_TOKENS:
            checkpoint = machine.copy(deepcopy_values=False)
            checkpoint_count = len(retained)
            checkpoint_depth = delimiter_depth
    return machine, retained, checkpoint, checkpoint_count, faults, fed


def syntax_diagnostics(
    source: str, error: SourceParseError, context: SourceContext
) -> tuple[Diagnostic, ...]:
    """Every independent syntax error of a failed parse, starting with ``error`` unchanged.

    Only grammar failures recover; structural and literal errors stay single.
    Recovered faults are kept only when recovery's first fault is ``error``'s
    own position, at most one per segment between ``;``/``{``/``}`` tokens,
    and at most ``max_syntax_errors`` before one ``SOURCE_SYNTAX_ERROR_LIMIT``.
    """

    first = error.to_diagnostic()
    if not isinstance(error.__cause__, UnexpectedInput):
        return (first,)
    limit = context.source_limits.max_syntax_errors
    budget = _FAULTS_PER_ERROR * limit
    lexed: list[_Fault] = []
    parsed: list[_Fault] = []
    tokens: tuple[Token, ...] = ()
    exhausted = False
    try:
        tokens, faults = lex_tokens(source, context, max_faults=budget, record=lexed)
        machine, _, _, _, faults, fed = retain_tokens(
            tokens, context, faults, max_faults=budget, source=source, record=parsed
        )
        # After an earlier fault, a missing `}` at the end is nearly always its cascade.
        if fed and not faults and "$END" not in machine.accepts():
            try:
                machine.feed_eof()
            except UnexpectedInput as exc:
                parsed.append((len(source), unexpected_error(exc, context.filename, source)))
    except SourceLimitError:
        exhausted = True
    except SourceParseError:
        return (first,)
    boundaries = [token.start_pos or 0 for token in tokens if token.type in BOUNDARY_TOKENS]
    segments: set[int] = set()
    found: list[SourceParseError] = []
    for offset, fault in sorted((*lexed, *parsed), key=lambda item: item[0]):
        segment = bisect_left(boundaries, offset)
        if segment not in segments:
            segments.add(segment)
            found.append(fault)
    if not found or (found[0].line, found[0].column) != (first.line, first.column):
        return (first,)
    diagnostics = [first, *(fault.to_diagnostic() for fault in found[1:])]
    if len(diagnostics) > limit or exhausted:
        marker = diagnostics[limit] if len(diagnostics) > limit else diagnostics[-1]
        diagnostics = [
            *diagnostics[:limit],
            replace(
                marker,
                code="SOURCE_SYNTAX_ERROR_LIMIT",
                message=f"syntax checking stopped after {min(limit, len(diagnostics))} errors",
                help=None,
                fixes=(),
            ),
        ]
    return tuple(diagnostics)
