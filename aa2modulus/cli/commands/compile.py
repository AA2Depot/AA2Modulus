"""``compile``: turn unified ``.aa2m`` source into an extensionless module."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from ...app.compile import CompileError, compile_source_with_warnings
from ...context.limits import SourceLimits
from ...core.diagnostics import Diagnostic, exit_code_for_diagnostics
from ...metadata.loader import load_metadata
from ...metadata.schema import MetadataError
from ..arguments import report_options, source_limit_options
from ..common import (
    DEFAULT_SETTINGS,
    EXIT_INPUT_ERROR,
    EXIT_INTERNAL_ERROR,
    EXIT_OK,
    read_source,
    report,
    summary,
)
from ..render.terminal import ReportSettings


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "compile",
        help="compile unified `.aa2m` source to an extensionless module",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    source_limit_options(parser)
    report_options(parser)


def run(
    args: argparse.Namespace, settings: ReportSettings, source_limits: SourceLimits | None
) -> int:
    return compile_source_file(
        args.source,
        args.output,
        output=sys.stdout,
        errors=sys.stderr,
        source_limits=source_limits,
        settings=settings,
    )


def compile_source_file(
    source_path: Path,
    output_path: Path,
    *,
    output: TextIO,
    errors: TextIO,
    source_limits: SourceLimits | None = None,
    settings: ReportSettings = DEFAULT_SETTINGS,
) -> int:
    source, exit_code = read_source(source_path, errors, source_limits=source_limits)
    if source is None:
        return exit_code
    try:
        metadata = load_metadata()
        if source_path.suffix == ".aa2mi":
            failure = Diagnostic(
                str(source_path),
                1,
                1,
                "error",
                "LIBRARY_COMPILE",
                "library files cannot be compiled as modules",
            )
            report(
                (failure,),
                errors,
                settings,
                sources={str(source_path): source},
                summary="compilation failed: 1 error",
            )
            return EXIT_INPUT_ERROR
        data, warnings = compile_source_with_warnings(
            source,
            filename=str(source_path),
            metadata=metadata,
            source_limits=source_limits,
            import_base=source_path.resolve().parent,
        )
    except MetadataError as exc:
        print(f"metadata error: {exc}", file=errors)
        return EXIT_INTERNAL_ERROR
    except CompileError as exc:
        report(
            exc.diagnostics,
            errors,
            settings,
            sources={str(source_path): source},
            summary=summary("compilation failed", exc.diagnostics, "compiled"),
        )
        return int(exit_code_for_diagnostics(exc.diagnostics))

    try:
        output_path.write_bytes(data)
    except OSError as exc:
        print(f"could not write module {output_path}: {exc}", file=errors)
        return EXIT_INPUT_ERROR
    report(
        warnings,
        errors,
        settings,
        sources={str(source_path): source},
        summary=summary("compilation failed", warnings, "compiled"),
    )
    print(f"compiled: {source_path} -> {output_path}", file=output)
    return EXIT_OK
