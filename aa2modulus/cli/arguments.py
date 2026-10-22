"""Argument builders shared by the command parsers."""

from __future__ import annotations

import argparse

from ..context.limits import SourceLimits
from .render.terminal import ReportSettings


def _nonnegative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return value


def source_limit_options(parser: argparse.ArgumentParser) -> None:
    defaults = SourceLimits()
    group = parser.add_argument_group(
        "source limits", "raise only for unusually large or deeply nested source"
    )
    for option, field, description in (
        ("--max-source-chars", "max_source_chars", "Unicode source characters"),
        ("--max-source-nodes", "max_nodes", "nodes per parse/AST/HIR stage"),
        (
            "--max-binding-work",
            "max_binding_work",
            "aggregate expression binding and overload work",
        ),
        ("--max-binding-errors", "max_binding_errors", "binding errors reported (minimum 1)"),
        ("--max-syntax-errors", "max_syntax_errors", "syntax errors reported (minimum 1)"),
        ("--max-syntax-depth", "max_syntax_depth", "syntax depth (ceiling 512)"),
        ("--max-source-nesting", "max_nesting_depth", "statement/expression nesting (ceiling 128)"),
        ("--max-macro-nodes", "max_expansion_nodes", "aggregate macro expansion node work"),
        ("--max-macro-depth", "max_macro_depth", "macro call depth (ceiling 128)"),
        ("--max-import-files", "max_import_files", "unique imported libraries"),
        ("--max-import-depth", "max_import_depth", "library import edges on a path"),
        (
            "--max-total-source-chars",
            "max_total_source_chars",
            "characters across the source graph",
        ),
    ):
        default = getattr(defaults, field)
        group.add_argument(
            option,
            dest=field,
            type=_nonnegative_int,
            default=default,
            help=f"maximum {description} (default: {default})",
        )


def report_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="color diagnostics: auto colors a terminal unless NO_COLOR is set (default: auto)",
    )
    parser.add_argument(
        "--diagnostic-format",
        choices=("human", "short"),
        default="human",
        help="diagnostic layout: snippets (human) or one line each (short) (default: human)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show binary offsets and structural paths as evidence",
    )


def source_limits_from_args(args: argparse.Namespace) -> SourceLimits:
    """Build the limits chosen by ``source_limit_options``; ``ValueError`` if invalid."""

    return SourceLimits(
        max_source_chars=args.max_source_chars,
        max_nodes=args.max_nodes,
        max_binding_work=args.max_binding_work,
        max_binding_errors=args.max_binding_errors,
        max_syntax_errors=args.max_syntax_errors,
        max_syntax_depth=args.max_syntax_depth,
        max_nesting_depth=args.max_nesting_depth,
        max_expansion_nodes=args.max_expansion_nodes,
        max_macro_depth=args.max_macro_depth,
        max_import_files=args.max_import_files,
        max_import_depth=args.max_import_depth,
        max_total_source_chars=args.max_total_source_chars,
    )


def report_settings_from_args(args: argparse.Namespace) -> ReportSettings:
    """Collect the choices made by ``report_options``."""

    return ReportSettings(args.diagnostic_format, args.color, args.verbose)
