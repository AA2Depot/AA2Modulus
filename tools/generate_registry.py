"""Generate the metadata registry from the pinned AAUnlimited source

Reads a clean AAUnlimited source checkout at the pinned revision, given with
--source-root, and writes aa2modulus/metadata/registry/. With --check, compares instead of writing.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aa2modulus.metadata.loader import load_metadata
from tools.registry import source, tables, writer

REGISTRY = ROOT / "aa2modulus/metadata/registry"


def generate(checkout: Path) -> dict[str, bytes]:
    """Registry file name -> bytes, validated by the runtime loader."""

    checkout = checkout.resolve()
    source.check_checkout(checkout)

    documents = {
        "actions.json": tables.actions(checkout),
        "events.json": tables.events(checkout),
        "expressions.json": tables.expressions(checkout),
        "named_constants.json": tables.named_constants(checkout),
    }

    # The manifest pins every file read
    hashed = sorted({*source.FILES, *source.ENUM_FILES})
    files = writer.render(documents, {file: source.sha256(checkout, file) for file in hashed})

    # Validate with the same loader the runtime uses
    with tempfile.TemporaryDirectory(prefix="aa2modulus-registry-") as temporary:
        for name, data in files.items():
            (Path(temporary) / name).write_bytes(data)
        load_metadata(temporary)

    return files


def differences(directory: Path, files: dict[str, bytes]) -> list[str]:
    actual = {path.name for path in directory.glob("*.json")}

    problems = [f"missing: {name}" for name in sorted(files.keys() - actual)]
    problems += [f"extra: {name}" for name in sorted(actual - files.keys())]
    problems += [
        f"stale: {name}"
        for name in sorted(files.keys() & actual)
        if (directory / name).read_bytes() != files[name]
    ]

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the metadata registry")
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="existing clean AAUnlimited source checkout at the pinned revision",
    )
    parser.add_argument("--output-dir", type=Path, default=REGISTRY)
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    arguments = parser.parse_args()
    output = arguments.output_dir

    try:
        files = generate(arguments.source_root)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"registry generation failed: {error}\n")

    if arguments.check:
        problems = differences(output, files)
        if problems:
            parser.exit(1, "registry is not current:\n" + "".join(f"  {p}\n" for p in problems))
        print(f"verified {len(files)} files in {output}")
        return

    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (output / name).write_bytes(data)
    print(f"wrote {len(files)} files in {output}")


if __name__ == "__main__":
    main()
