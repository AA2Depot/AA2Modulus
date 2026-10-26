"""Merge per-target release manifest fragments into one release asset

Each build job writes a fragment with the frozen binary's
``editor-data manifest``. The fragments must be identical; the merged file adds
the sorted ``platforms`` that built. Standard library only, so the release job
needs no project environment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "aa2modulus.release-manifest.v1"
# The targets tools/build.py produces.
TARGETS = frozenset({"linux-x64", "windows-x64"})


def fragment_argument(value: str) -> tuple[str, Path]:
    target, separator, path = value.partition("=")
    if not separator or not path:
        raise argparse.ArgumentTypeError(f"expected TARGET=PATH, got {value!r}")
    if target not in TARGETS:
        raise argparse.ArgumentTypeError(f"unknown target {target!r}")
    return target, Path(path)


def merged_manifest(fragments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Raise ``ValueError`` unless every fragment carries the schema and equals the others."""

    (first_target, first), *others = sorted(fragments.items())
    if first.get("schema") != SCHEMA:
        raise ValueError(f"{first_target}: schema is {first.get('schema')!r}, expected {SCHEMA!r}")
    for target, fragment in others:
        if fragment != first:
            raise ValueError(f"{target} manifest differs from {first_target}")
    return {**first, "platforms": sorted(fragments)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge release manifest fragments")
    parser.add_argument(
        "--fragment",
        type=fragment_argument,
        action="append",
        required=True,
        metavar="TARGET=PATH",
        help="a target's fragment; repeat once per target",
    )
    parser.add_argument("--output", type=Path, required=True, help="merged manifest file")
    arguments = parser.parse_args()

    targets = [target for target, _ in arguments.fragment]
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    if duplicates:
        parser.error(f"duplicate target {', '.join(duplicates)}")
    try:
        fragments = {
            target: json.loads(path.read_text(encoding="utf-8"))
            for target, path in arguments.fragment
        }
        manifest = merged_manifest(fragments)
    except (OSError, ValueError) as error:
        parser.exit(1, f"release manifest failed: {error}\n")

    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    arguments.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {arguments.output} for {', '.join(manifest['platforms'])}")


if __name__ == "__main__":
    main()
