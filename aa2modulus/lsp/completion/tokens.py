"""Token-level view of an incomplete source prefix: lexing, grammar state and positions."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from copy import copy
from dataclasses import dataclass

from lark import Lark, Token
from lark.exceptions import UnexpectedInput
from lark.parsers.lalr_analysis import Shift

from ...context.limits import SourceLimitError
from ...context.operation import SourceContext
from ...pipeline.analysis import SourceAnalysis
from ...pipeline.authoring import editor_prefix
from ...syntax.lexicon import terminal_literals
from ...syntax.limits import check_source_text
from ...syntax.parser.engine import shared_parser
from ...syntax.parser.errors import SourceParseError
from ...syntax.recovery import BOUNDARY_TOKENS

_NAME_SUFFIX = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\Z")
NAME_TOKENS = frozenset({"IDENT", "QUALIFIED_NAME"})


_EXPRESSION_START = frozenset(
    {
        "BOOLEAN",
        "ESCAPED_STRING",
        "FLOAT_BITS",
        "IDENT",
        "LPAR",
        "NOT_OP",
        "QUALIFIED_NAME",
        "RAW_EXPRESSION",
        "SIGNED_FLOAT",
        "SIGNED_INT",
        "VARIABLE",
    }
)
_STATEMENT_START = frozenset(
    {
        "FOR",
        "IF",
        "LOOP",
        "LOOP_KEYWORD",
        "RAW_ACTION",
        "STANDALONE_ELSE",
        "STANDALONE_ELSEIF",
    }
)


_PARTIAL_NAME_SUFFIX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\.?\Z")


@dataclass(frozen=True, slots=True)
class Prefix:
    parser: Lark
    expected: frozenset[str]
    suffix: str
    start: int
    tokens: tuple[Token, ...]


def lex_tokens(source: str, offset: int, context: SourceContext) -> tuple[Token, ...] | None:
    """Lex through the fixed grammar, rejecting cursor positions in ignored text."""

    limits = context.source_limits
    if limits.max_nodes <= 0:
        return None
    parser = shared_parser()
    prefix = source[:offset]
    try:
        tokens_list: list[Token] = []
        for token in parser.lex(prefix):
            # The compiler's parse tree contains at least one root plus each
            # token, so this conservative bound prevents oversized token tuples.
            if len(tokens_list) + 2 > limits.max_nodes:
                return None
            tokens_list.append(token)
    except (UnexpectedInput, ValueError):
        return None
    tokens = tuple(tokens_list)
    # Validate gaps against the same ignored patterns used by Lark. This allows
    # complete comments between tokens and suppresses a cursor in a trailing one.
    terminals_by_name = {terminal.name: terminal for terminal in parser.terminals}
    ignored = [
        (name, re.compile(terminals_by_name[name].pattern.to_regexp()), terminals_by_name[name])
        for name in parser.parser.lexer_conf.ignore
        if name in terminals_by_name and name != "WS"
    ]

    def skip_ignored(start: int, end: int) -> tuple[bool, bool]:
        cursor = start
        trailing_line_comment = False
        while cursor < end:
            if prefix[cursor].isspace():
                if prefix[cursor] in "\r\n":
                    trailing_line_comment = False
                cursor += 1
                continue
            match = next(
                (
                    (name, match, terminal)
                    for name, pattern, terminal in ignored
                    if (match := pattern.match(prefix, cursor, end))
                ),
                None,
            )
            if match is None or match[1].end() == cursor:
                return False, trailing_line_comment
            name, matched, terminal = match
            raw_pattern = str(terminal.pattern.value)
            trailing_line_comment = (
                name != "WS" and raw_pattern.startswith(r"\/\/") and matched.end() == end
            )
            cursor = matched.end()
        return True, trailing_line_comment

    cursor = 0
    for token in tokens:
        start = token.start_pos if token.start_pos is not None else cursor
        if not skip_ignored(cursor, start)[0]:
            return None
        cursor = token.end_pos if token.end_pos is not None else start + len(token)
    if cursor < offset:
        allowed, in_line_comment = skip_ignored(cursor, offset)
        if not allowed or in_line_comment:
            return None
    paren_depth = 0
    for token in tokens:
        if token.type == "LPAR":
            paren_depth += 1
            if paren_depth > limits.max_nesting_depth:
                return None
        elif token.type == "RPAR" and paren_depth:
            paren_depth -= 1
    return tokens


def contextual_tokens(
    parser: Lark, tokens: tuple[Token, ...]
) -> tuple[tuple[Token, ...], frozenset[str]] | None:
    """Feed basic-lexer tokens using exact literal terminals accepted by the grammar.

    ``accepts()`` copies the parser once per candidate terminal, so it runs only
    for a token the parse table does not take as lexed.
    """

    interactive = parser.parse_interactive()
    # Only the parser state matters here; building parse trees would double the work.
    interactive.parser_state.parse_conf = copy(interactive.parser_state.parse_conf)
    interactive.parser_state.parse_conf.callbacks = {}
    terminals = {terminal.name: terminal for terminal in parser.terminals}
    normalized: list[Token] = []
    for token in tokens:
        action = interactive.choices().get(token.type)
        if action is not None:
            # A shift always succeeds; a reduce can still reject the token after
            # LALR lookahead merging, so keep the state to retry from.
            fallback = None if action[0] is Shift else interactive.copy(deepcopy_values=False)
            try:
                interactive.feed_token(token)
            except UnexpectedInput:
                if fallback is None:
                    return None
                interactive = fallback
            else:
                normalized.append(token)
                continue
        accepted = interactive.accepts()
        if token.type not in accepted:
            matching = [
                terminal
                for name in accepted
                if (terminal := terminals.get(name)) is not None
                and terminal.pattern is not None
                and terminal.pattern.type == "str"
                and re.fullmatch(terminal.pattern.to_regexp(), str(token)) is not None
            ]
            if len(matching) != 1:
                return None
            token = Token.new_borrow_pos(matching[0].name, str(token), token)
        try:
            interactive.feed_token(token)
        except UnexpectedInput:
            return None
        normalized.append(token)
    return tuple(normalized), frozenset(interactive.accepts())


def _trailing_qualifier(tokens: tuple[Token, ...], offset: int) -> bool:
    """Whether the cursor directly follows an unspaced ``name.`` pair."""

    if len(tokens) < 2 or tokens[-1].type != "DOT" or tokens[-2].type not in NAME_TOKENS:
        return False
    name, dot = tokens[-2], tokens[-1]
    return (
        dot.end_pos == offset
        and name.end_pos == dot.start_pos
        and _NAME_SUFFIX.fullmatch(str(name)) is not None
    )


def build_prefix(
    source: str,
    offset: int,
    context: SourceContext,
    *,
    analysis: SourceAnalysis | None = None,
) -> Prefix | None:
    """The parser state and partly typed name before ``offset``.

    ``None`` when the source exceeds its size limit or the prefix cannot be recovered.
    """

    # Enforce the same source-size boundary before invoking either Lark lexer.
    try:
        check_source_text(source, filename=context.filename, limits=context.source_limits)
    except SourceLimitError:
        return None
    if (
        analysis is not None
        and analysis.source == source
        and isinstance(analysis.failure, SourceLimitError)
    ):
        return None
    offset = min(max(offset, 0), len(source))
    tokens = lex_tokens(source, offset, context)
    suffix = ""
    start = offset
    if tokens is None:
        match = _PARTIAL_NAME_SUFFIX.search(source[:offset])
        if match is not None:
            start = match.start()
            suffix = match.group()
        tokens = lex_tokens(source, start, context)
        if tokens is None:
            try:
                recovered = editor_prefix(source[:start], context)
            except (SourceLimitError, SourceParseError):
                return None
            return Prefix(shared_parser(), recovered.expected, suffix, start, recovered.tokens)
    elif _trailing_qualifier(tokens, offset):
        # ``name.`` lexes as a name plus the postfix DOT; it is still a qualified
        # name being typed, exactly like ``name.Part``.
        name = tokens[-2]
        suffix = f"{name}."
        start = name.start_pos if name.start_pos is not None else offset - len(suffix)
        tokens = tokens[:-2]
    elif tokens and tokens[-1].type in NAME_TOKENS:
        token = tokens[-1]
        token_start = token.start_pos if token.start_pos is not None else offset - len(token)
        token_end = token.end_pos if token.end_pos is not None else token_start + len(token)
        if token_end == offset and _NAME_SUFFIX.fullmatch(str(token)):
            suffix = str(token)
            start = token_start
            tokens = tokens[:-1]
    parser = shared_parser()
    parsed_prefix = contextual_tokens(parser, tokens)
    if parsed_prefix is None:
        try:
            recovered = editor_prefix(source[:start], context)
        except (SourceLimitError, SourceParseError):
            return None
        return Prefix(parser, recovered.expected, suffix, start, recovered.tokens)
    tokens, expected = parsed_prefix
    return Prefix(parser, expected, suffix, start, tokens)


def classify_following(parser: Lark, source: str, end: int) -> tuple[bool, bool, Token | None]:
    """Classify the first token after the replaced range."""

    try:
        following = next(iter(parser.lex(source[end:])), None)
    except UnexpectedInput:
        return False, False, None
    return (
        following is not None and following.type == "LPAR",
        following is not None and following.type in {"SEMICOLON", "LBRACE"},
        following,
    )


def literal_keywords(parser: Lark, expected: Iterable[str]) -> tuple[str, ...]:
    by_name = {terminal.name: terminal for terminal in parser.terminals}
    values = {
        value
        for name in expected
        if (terminal := by_name.get(name)) is not None
        for value in terminal_literals(terminal)
        if all(part.isidentifier() for part in value.split("."))
    }
    return tuple(sorted(values, key=str.casefold))


def positions(prefix: Prefix) -> tuple[bool, bool, bool]:
    expected = prefix.expected
    # Literal-only grammar states (notably global initializers) share some
    # literal terminals with expressions but do not accept source names.
    expression_position = bool(expected & _EXPRESSION_START & {"QUALIFIED_NAME"})
    statement_position = bool(expected & _STATEMENT_START)
    event_position = bool(prefix.tokens and prefix.tokens[-1].type == "ON")
    if statement_position:
        expression_position = False
    return expression_position, statement_position, event_position


def statement_context(tokens: tuple[Token, ...]) -> bool:
    parsed = contextual_tokens(shared_parser(), tokens)
    return parsed is not None and bool(parsed[1] & _STATEMENT_START)


def last_boundary(tokens: Sequence[Token], breaks: frozenset[str] = BOUNDARY_TOKENS) -> int:
    """Index of the last token whose type is in ``breaks``, or -1 when there is none."""

    return max((index for index, token in enumerate(tokens) if token.type in breaks), default=-1)
