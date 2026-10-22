"""``inspect``: decode an extensionless module and print a readable description."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal, TextIO

from ...binary.reader import DecodeError, decode_module
from ...context.limits import SourceLimits
from ...context.operation import SourceContext
from ...core.diagnostics import binary_diagnostic, exit_code_for_inspection
from ...metadata.loader import load_metadata
from ...metadata.schema import MetadataError
from ...validation.validator.module import validate_module
from ..arguments import report_options
from ..common import (
    DEFAULT_SETTINGS,
    EXIT_INPUT_ERROR,
    EXIT_INTERNAL_ERROR,
    EXIT_USAGE_ERROR,
    report,
)
from ..inspection import write_inspection
from ..render.terminal import ReportSettings, render_options


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "inspect",
        help="inspect an extensionless AAUnlimited module",
    )
    parser.add_argument("module", type=Path)
    parser.add_argument(
        "--validation-profile",
        choices=("strict", "native"),
        default="strict",
        help="semantic validation profile (default: strict)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on semantic diagnostics or trailing bytes",
    )
    report_options(parser)


def run(
    args: argparse.Namespace, settings: ReportSettings, source_limits: SourceLimits | None
) -> int:
    return inspect_module(
        args.module,
        strict=args.strict,
        validation_profile=args.validation_profile,
        output=sys.stdout,
        errors=sys.stderr,
        settings=settings,
    )


def inspect_module(
    path: Path,
    *,
    strict: bool,
    validation_profile: Literal["strict", "native"] = "strict",
    output: TextIO,
    errors: TextIO,
    settings: ReportSettings = DEFAULT_SETTINGS,
) -> int:
    if not path.is_file():
        print(f"input module does not exist: {path}", file=errors)
        return EXIT_USAGE_ERROR

    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"could not read module {path}: {exc}", file=errors)
        return EXIT_INPUT_ERROR

    try:
        decoded = decode_module(data, reject_trailing=strict)
    except DecodeError as exc:
        failure = binary_diagnostic(str(path), exc, code="DECODE_ERROR")
        report((failure,), errors, settings, summary=f"invalid module {path}: 1 error")
        return EXIT_INPUT_ERROR

    try:
        metadata = load_metadata()
        # The language catalog lets messages use source spellings.
        catalog = SourceContext.create(metadata=metadata).catalog
    except MetadataError as exc:
        print(f"metadata error: {exc}", file=errors)
        return EXIT_INTERNAL_ERROR

    validation = validate_module(
        decoded.module,
        metadata=metadata,
        catalog=catalog,
        filename=str(path),
        profile=validation_profile,
    )
    resolved = metadata.resolve_module(decoded.module)
    write_inspection(
        resolved,
        validation,
        trailing_bytes=decoded.trailing_bytes,
        output=output,
        options=render_options(settings, output),
    )

    return int(
        exit_code_for_inspection(
            validation.diagnostics,
            strict=strict,
            has_trailing_bytes=decoded.trailing_bytes is not None,
        )
    )
