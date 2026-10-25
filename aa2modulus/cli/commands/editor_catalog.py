"""``editor-catalog``: print the built-ins catalog that editor clients read as ``builtins.json``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import BinaryIO, TextIO

from ...app.editor_catalog.document import editor_catalog, render
from ...context.limits import SourceLimits
from ...metadata.schema import MetadataError
from ..common import EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR, EXIT_OK
from ..render.terminal import ReportSettings


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "editor-catalog",
        help="print the built-ins catalog for editor clients as JSON",
        description=(
            "Print the built-ins catalog (builtins.json) that editor clients read. "
            "The build report goes to stderr."
        ),
    )
    parser.add_argument("-o", "--output", type=Path, help="write the catalog to this file")


def run(
    args: argparse.Namespace, settings: ReportSettings, source_limits: SourceLimits | None
) -> int:
    return write_editor_catalog(args.output, output=sys.stdout.buffer, errors=sys.stderr)


def write_editor_catalog(output_path: Path | None, *, output: BinaryIO, errors: TextIO) -> int:
    """Write the catalog as UTF-8 with LF line ends, whatever the console encoding."""

    try:
        document, report = editor_catalog()
    except MetadataError as exc:
        print(f"metadata error: {exc}", file=errors)
        return EXIT_INTERNAL_ERROR
    print("\n".join(report.lines()), file=errors)
    data = render(document).encode("utf-8")
    if output_path is None:
        output.write(data)
        output.flush()
        return EXIT_OK
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
    except OSError as exc:
        print(f"could not write catalog {output_path}: {exc}", file=errors)
        return EXIT_INPUT_ERROR
    print(f"wrote {len(document['entries'])} entries to {output_path}", file=errors)
    return EXIT_OK
