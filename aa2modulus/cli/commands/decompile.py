"""``decompile``: turn an extensionless module back into unified ``.aa2m`` source."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from ...app.decompile import decompile_module, trailing_bytes_diagnostic
from ...binary.reader import DecodeError
from ...context.limits import SourceLimits
from ...core.diagnostics import binary_diagnostic, has_errors
from ...decompile.format.text import FormatError
from ...metadata.loader import load_metadata
from ...metadata.schema import MetadataError
from ...model.records import Module
from ..arguments import report_options
from ..common import (
    DEFAULT_SETTINGS,
    EXIT_INPUT_ERROR,
    EXIT_INTERNAL_ERROR,
    EXIT_OK,
    EXIT_USAGE_ERROR,
    report,
)
from ..render.diagnostics import count_text
from ..render.terminal import ReportSettings


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "decompile",
        help="decompile an extensionless module to unified `.aa2m` source",
    )
    parser.add_argument("module", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    report_options(parser)


def run(
    args: argparse.Namespace, settings: ReportSettings, source_limits: SourceLimits | None
) -> int:
    return decompile_module_file(
        args.module,
        args.output,
        output=sys.stdout,
        errors=sys.stderr,
        settings=settings,
    )


def _resolved_module(module: Module) -> Module:
    """Attach metadata so breadcrumbs can name actions; keep the bare module on failure."""

    try:
        return load_metadata().resolve_module(module)
    except (MetadataError, ValueError):
        return module


def decompile_module_file(
    input_path: Path,
    output_path: Path | None,
    output: TextIO,
    errors: TextIO,
    *,
    settings: ReportSettings = DEFAULT_SETTINGS,
) -> int:
    if not input_path.is_file():
        print(f"input module does not exist: {input_path}", file=errors)
        return EXIT_USAGE_ERROR
    source_name = str(output_path) if output_path is not None else "<stdout>"
    try:
        data = input_path.read_bytes()
        result = decompile_module(
            data,
            filename=str(input_path),
            source_filename=source_name,
        )
    except MetadataError as exc:
        print(f"metadata error: {exc}", file=errors)
        return EXIT_INTERNAL_ERROR
    except DecodeError as exc:
        failure = binary_diagnostic(str(input_path), exc, code="DECODE_ERROR")
        report((failure,), errors, settings, summary=f"could not decompile {input_path}: 1 error")
        return EXIT_INPUT_ERROR
    except (OSError, FormatError) as exc:
        print(f"could not decompile {input_path}: {exc}", file=errors)
        return EXIT_INPUT_ERROR
    diagnostics = result.diagnostics
    if result.decoded.trailing_bytes is not None:
        diagnostics += (trailing_bytes_diagnostic(str(input_path), result.decoded.trailing_bytes),)
    counts = count_text(diagnostics)
    summary = None
    if counts:
        summary = f"decompiled {input_path} -> {source_name} with {counts}"
        if has_errors(diagnostics):
            summary += "; the source will not compile until it is fixed"
        elif any(item.code == "UNDEFINED_VARIABLE" for item in diagnostics):
            summary += "; declare the suggested globals before compiling"
    needs_module = any(item.is_binary_only and item.path for item in diagnostics)
    report(
        diagnostics,
        errors,
        settings,
        sources={source_name: result.source},
        module=_resolved_module(result.decoded.module) if needs_module else None,
        summary=summary,
    )
    if output_path is None:
        output.write(result.source)
    else:
        try:
            output_path.write_text(result.source, encoding="utf-8")
        except OSError as exc:
            print(f"could not write source {output_path}: {exc}", file=errors)
            return EXIT_INPUT_ERROR
        print(f"decompiled: {input_path} -> {output_path}", file=output)
    return EXIT_OK
