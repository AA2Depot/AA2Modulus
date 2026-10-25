"""``editor-data``: print the built-ins catalog or the lexicon that editor clients read."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import BinaryIO, TextIO

from ...app.editor_catalog.document import editor_catalog, render
from ...app.editor_lexicon import editor_lexicon
from ...context.limits import SourceLimits
from ...metadata.schema import MetadataError
from ..common import EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR, EXIT_OK
from ..render.terminal import ReportSettings


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "editor-data",
        help="print editor client data (built-ins catalog or lexicon) as JSON",
        description=(
            "Print a document that editor clients read: 'catalog' is the built-ins "
            "catalog (builtins.json), 'lexicon' is the lexical surface of the grammar "
            "with its fingerprint. Reports go to stderr."
        ),
    )
    parser.add_argument("document", choices=("catalog", "lexicon"), help="document to print")
    parser.add_argument("-o", "--output", type=Path, help="write the document to this file")


def run(
    args: argparse.Namespace, settings: ReportSettings, source_limits: SourceLimits | None
) -> int:
    return write_editor_data(
        args.document, args.output, output=sys.stdout.buffer, errors=sys.stderr
    )


def write_editor_data(
    document_name: str, output_path: Path | None, *, output: BinaryIO, errors: TextIO
) -> int:
    """Write the document as UTF-8 with LF line ends, whatever the console encoding."""

    try:
        if document_name == "catalog":
            document, report = editor_catalog()
            print("\n".join(report.lines()), file=errors)
            summary = f"{len(document['entries'])} entries"
        else:
            document = editor_lexicon()
            summary = f"lexicon {document['fingerprint']}"
    except MetadataError as exc:
        print(f"metadata error: {exc}", file=errors)
        return EXIT_INTERNAL_ERROR
    data = render(document).encode("utf-8")
    if output_path is None:
        output.write(data)
        output.flush()
        return EXIT_OK
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
    except OSError as exc:
        print(f"could not write {document_name} {output_path}: {exc}", file=errors)
        return EXIT_INPUT_ERROR
    print(f"wrote {summary} to {output_path}", file=errors)
    return EXIT_OK
