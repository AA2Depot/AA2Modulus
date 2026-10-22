"""Export the portable language reference bundle

Builds a self-contained documentation bundle (guides, grammar, examples, and
every built-in as reference.md and reference.json) from the committed
contracts, examples, registry and language policy; it never reads the AAUnlimited source.
Nothing in the repository consumes it; it is source material for a future
website, so --output-dir is required. With --check, compares instead of writing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.reference import bundle, records


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the portable language reference bundle")
    parser.add_argument("--output-dir", type=Path, required=True, help="bundle directory")
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    arguments = parser.parse_args()
    output = arguments.output_dir

    try:
        files = bundle.files(ROOT, records.build(ROOT))
    except (OSError, ValueError) as error:
        parser.exit(1, f"reference export failed: {error}\n")

    if arguments.check:
        problems = bundle.differences(output, files)
        if problems:
            parser.exit(
                1, "reference bundle is not current:\n" + "".join(f"  {p}\n" for p in problems)
            )
        print(f"verified {len(files)} files in {output}")
        return

    bundle.write(output, files)
    print(f"wrote {len(files)} files in {output}")


if __name__ == "__main__":
    main()
