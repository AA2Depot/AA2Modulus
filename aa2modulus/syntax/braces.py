"""Hints that point syntax errors caused by an unbalanced brace at the likely cause.

The parser reports a brace fault where it notices it, often far from the brace
at fault. The hint names the first ``{``/``}`` pair whose lines are indented
differently. It is a guess, so it never moves the error, and it is added only
when a brace fault is certain: the braces do not balance, or a module closed
before a top-level trigger.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from lark import Token

from ..context.limits import SourceLimitError
from ..context.operation import SourceContext
from ..core.diagnostics import Diagnostic
from ..core.locations import RelatedLocation
from .parser.errors import SourceParseError
from .parser.spans import token_span
from .recovery import lex_tokens


def brace_hints(
    source: str, diagnostics: Sequence[Diagnostic], context: SourceContext
) -> tuple[Diagnostic, ...]:
    """Add a brace hint to the first error at or after the suspect ``{``."""

    try:
        tokens, _ = lex_tokens(source, context)
    except (SourceLimitError, SourceParseError):
        return tuple(diagnostics)
    opened: list[Token] = []
    suspect: tuple[Token, Token] | None = None
    stray = False
    for token in tokens:
        if token.type == "LBRACE":
            opened.append(token)
            continue
        if token.type != "RBRACE":
            continue
        if not opened:
            stray = True
            continue
        start = opened.pop()
        if suspect is None and _misaligned(source, start, token):
            suspect = (start, token)
    module_closed = any(item.code == "TEMPLATE_LIBRARY_ONLY" for item in diagnostics)
    if not (stray or opened or module_closed):
        return tuple(diagnostics)
    if suspect is not None:
        start, end = suspect
        hint = (
            f"the `{{` on line {start.line} and the `}}` on line {end.line} are indented "
            f"differently; a `}}` is probably missing or extra between them"
        )
        related: tuple[RelatedLocation, ...] = (
            RelatedLocation(
                token_span(start, context.filename), f"this `{{` is closed on line {end.line}"
            ),
            RelatedLocation(
                token_span(end, context.filename), f"this `}}` closes the `{{` on line {start.line}"
            ),
        )
    elif opened:
        start = opened[-1]
        hint = f"the `{{` on line {start.line} is never closed"
        related = (
            RelatedLocation(token_span(start, context.filename), "this `{` is never closed"),
        )
    else:
        return tuple(diagnostics)
    result = list(diagnostics)
    for index, item in enumerate(result):
        if item.is_error and (item.line, item.column) >= (start.line, start.column):
            result[index] = (
                replace(item, help=hint, related=(*item.related, *related))
                if item.help is None
                else replace(item, notes=(*item.notes, hint), related=(*item.related, *related))
            )
            break
    return tuple(result)


def _misaligned(source: str, start: Token, end: Token) -> bool:
    """Whether a ``}`` that opens its line is indented unlike its ``{`` line."""

    if end.line == start.line:
        return False
    closing = source[source.rfind("\n", 0, end.start_pos) + 1 : end.start_pos]
    if closing.strip():
        return False
    line_start = source.rfind("\n", 0, start.start_pos) + 1
    opening = source[line_start : start.start_pos]
    return closing != opening[: len(opening) - len(opening.lstrip())]
