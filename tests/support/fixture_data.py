"""Inventory and integrity hashes for the retained native inputs."""

from __future__ import annotations

import json

from tests.support.paths import MODULE_FIXTURES


def fixture_inventory() -> dict[str, str]:
    manifest = json.loads((MODULE_FIXTURES / "sha256.json").read_text(encoding="utf-8"))
    binaries = {
        path.name for path in MODULE_FIXTURES.iterdir() if path.is_file() and not path.suffix
    }
    if not manifest or set(manifest) != binaries:
        raise ValueError(
            f"native fixture manifest mismatch: missing {sorted(binaries - set(manifest))}, "
            f"unexpected {sorted(set(manifest) - binaries)}"
        )
    return manifest


FIXTURE_HASHES = fixture_inventory()
MODULE_NAMES = tuple(sorted(FIXTURE_HASHES))
