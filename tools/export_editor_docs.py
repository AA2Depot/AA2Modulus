"""Export compiled-and-verified built-in documentation for editors

Writes builtins.json, one entry per source-spelled native row with signature,
description and an example that compiles. The editor repository owns the file,
so --output is required. With --check, compares instead of writing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from aa2modulus.context.operation import SourceContext
from tools.editor_docs import entries, examples
from tools.editor_docs.entries import Report

SCHEMA = "aa2modulus.editor-builtins.v1"
DOCS_WEBSITE = None


def build_editor_docs(*, context: SourceContext | None = None) -> tuple[dict[str, Any], Report]:
    context = context or SourceContext.create()
    report = Report()

    drafts = entries.build(context, report)
    examples.attach(context, drafts, report)

    document = {
        "schema": SCHEMA,
        "languageVersion": context.source_policy.language_version,
        "catalogFingerprint": context.catalog.fingerprint,
        "website": DOCS_WEBSITE,
        "entries": [draft.entry for draft in drafts],
    }
    return document, report


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def check_output(path: Path, document: dict[str, Any]) -> str | None:
    """Why ``path`` does not hold ``document``, or None when it does."""

    if not path.is_file():
        return f"missing: {path}"
    if path.read_text(encoding="utf-8") != render(document):
        return f"stale: {path}"
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export built-in documentation for editors")
    parser.add_argument("--output", type=Path, required=True, help="builtins.json to write")
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    arguments = parser.parse_args(argv)
    output = arguments.output

    try:
        document, report = build_editor_docs()
    except (OSError, ValueError) as error:
        parser.exit(1, f"editor documentation export failed: {error}\n")

    print("\n".join(report.lines()))

    if arguments.check:
        if problem := check_output(output, document):
            parser.exit(1, f"editor documentation is not current: {problem}\n")
        print(f"verified {len(document['entries'])} entries in {output}")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(document), encoding="utf-8", newline="\n")
    print(f"wrote {len(document['entries'])} entries in {output}")


if __name__ == "__main__":
    main()
