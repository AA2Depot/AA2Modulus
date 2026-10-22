"""The shared LALR parser built from the package grammar."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from lark import Lark, Token, Tree

from ...context.limits import SourceLimits, resolve_source_limits
from ..limits import check_source_text, check_source_tree

GRAMMAR_PATH = Path(__file__).resolve().parents[1] / "grammar" / "unified.lark"


def build_parser() -> Lark:
    """Build the unified source parser from the package-owned grammar."""

    return Lark(
        GRAMMAR_PATH.read_text(encoding="utf-8"),
        parser="lalr",
        lexer="contextual",
        propagate_positions=True,
        maybe_placeholders=False,
        start="start",
    )


_parser: Lark | None = None
_parser_lock = Lock()


def shared_parser() -> Lark:
    """Return the one fixed-grammar parser, constructing it on first use."""

    global _parser
    parser = _parser
    if parser is None:
        with _parser_lock:
            parser = _parser
            if parser is None:
                parser = build_parser()
                _parser = parser
    return parser


def parse_source_tree(
    source: str,
    *,
    filename: str = "<source>",
    source_limits: SourceLimits | None = None,
) -> Tree[Token]:
    """Parse unified source and return its positioned syntax tree."""

    limits = resolve_source_limits(source_limits)
    check_source_text(source, filename=filename, limits=limits)
    tree = shared_parser().parse(source)
    check_source_tree(tree, filename=filename, limits=limits)
    return tree
