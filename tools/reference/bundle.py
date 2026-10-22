"""The portable reference bundle: its inputs and the files it contains"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import markdown

DOCS = ("grammar.md", "language.md", "metadata.md", "native-format.md")
GRAMMAR = Path("aa2modulus/syntax/grammar/unified.lark")

# Links rewritten so the copied guides work inside the bundle.
EXAMPLE_LINK = re.compile(r"\]\((?:\.\./)?examples/([^)#]+)(#[^)]+)?\)")
EXAMPLES_LINK = re.compile(r"\]\((?:\.\./)?examples\)")
QUICK_START_LINK = re.compile(r"\]\((?:\.\./)?README\.md#quick-start\)")

INDEX = """\
# `.aa2m` Language Reference Bundle

This directory is a portable documentation bundle for editor and extension authors. \
It has no runtime dependency on the `aa2modulus` package. The normative grammar and \
language guide are copied from the project's current contracts; metadata inventories \
and `reference.json` are generated from the committed registry and policy.

## Contents

- [Grammar guide](grammar.md)
- [Exact parser grammar](unified.lark)
- [Language guide](language.md)
- [Metadata policy and semantics](metadata.md)
- [Native format and runtime evidence](native-format.md)
- [Native actions, events, expressions and constants](reference.md)
- [Machine-readable reference](reference.json)
- [Examples](examples/index.md)

## Quick start

```aa2m
module "Notification Example" {
  trigger "On Card Added" {
    on CARD_ADDED;
    Notification("A card was added to class");
  }
}
```
"""


def examples(root: Path) -> list[Path]:
    """Example modules and libraries, sorted by path."""

    directory = root / "examples"
    paths = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix in {".aa2m", ".aa2mi"}
    ]
    return sorted(paths, key=lambda path: path.relative_to(directory).as_posix())


def _portable(guide: str) -> str:
    guide = EXAMPLES_LINK.sub("](examples/index.md)", guide)
    guide = EXAMPLE_LINK.sub(lambda match: f"](examples/{match[1]}{match[2] or ''})", guide)
    return QUICK_START_LINK.sub("](index.md#quick-start)", guide)


def files(root: Path, data: dict[str, Any]) -> dict[str, bytes]:
    """Bundle path -> bytes."""

    names = [path.relative_to(root / "examples").as_posix() for path in examples(root)]
    example_index = "# `.aa2m` Examples\n\n" + "".join(f"- [{n}](./{n})\n" for n in names)

    bundle = {
        "index.md": INDEX.encode(),
        "reference.json": (
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode(),
        "reference.md": markdown.render(data).encode(),
        "examples/index.md": example_index.encode(),
        "unified.lark": (root / GRAMMAR).read_bytes(),
    }
    for name in DOCS:
        bundle[name] = _portable((root / "docs" / name).read_text(encoding="utf-8")).encode()
    for name, path in zip(names, examples(root), strict=True):
        bundle[f"examples/{name}"] = path.read_bytes()

    return bundle


def differences(directory: Path, bundle: dict[str, bytes]) -> list[str]:
    actual = set()
    if directory.exists():
        actual = {
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        }

    problems = [f"missing: {name}" for name in sorted(bundle.keys() - actual)]
    problems += [f"extra: {name}" for name in sorted(actual - bundle.keys())]
    problems += [
        f"stale: {name}"
        for name in sorted(bundle.keys() & actual)
        if (directory / name).read_bytes() != bundle[name]
    ]

    return problems


def write(directory: Path, bundle: dict[str, bytes]) -> None:
    """Write every bundle file; files not in the bundle are kept."""

    for name, data in bundle.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
