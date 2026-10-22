"""``validate``: check unified ``.aa2m`` source without writing a module."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from ...app.compile import validate_source
from ...context.limits import SourceLimits
from ...core.diagnostics import exit_code_for_diagnostics
from ...metadata.loader import load_metadata
from ...metadata.schema import MetadataError
from ..arguments import report_options, source_limit_options
from ..common import (
    DEFAULT_SETTINGS,
    EXIT_INTERNAL_ERROR,
    EXIT_OK,
    read_source,
    report,
    summary,
)
from ..render.terminal import ReportSettings


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "validate",
        help="validate unified `.aa2m` source",
    )
    parser.add_argument("source", type=Path)
    source_limit_options(parser)
    report_options(parser)


def run(
    args: argparse.Namespace, settings: ReportSettings, source_limits: SourceLimits | None
) -> int:
    return validate_source_file(
        args.source,
        output=sys.stdout,
        errors=sys.stderr,
        source_limits=source_limits,
        settings=settings,
    )


def validate_source_file(
    path: Path,
    *,
    output: TextIO,
    errors: TextIO,
    source_limits: SourceLimits | None = None,
    settings: ReportSettings = DEFAULT_SETTINGS,
) -> int:
    source, exit_code = read_source(path, errors, source_limits=source_limits)
    if source is None:
        return exit_code
    try:
        metadata = load_metadata()
        result = validate_source(
            source,
            filename=str(path),
            metadata=metadata,
            source_limits=source_limits,
            import_base=path.resolve().parent,
            source_kind="library" if path.suffix == ".aa2mi" else "module",
        )
    except MetadataError as exc:
        print(f"metadata error: {exc}", file=errors)
        return EXIT_INTERNAL_ERROR

    report(
        result.diagnostics,
        errors,
        settings,
        sources={str(path): source},
        summary=summary("validation failed", result.diagnostics, "validation passed"),
    )
    if result.errors:
        return int(exit_code_for_diagnostics(result.diagnostics))
    print(f"valid: {path}", file=output)
    return EXIT_OK
