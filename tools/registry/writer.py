"""Registry files as bytes, with the manifest that indexes them"""

from __future__ import annotations

import json
from typing import Any

from aa2modulus.metadata.schema import GENERATOR_VERSION, MANIFEST_SCHEMA

from .source import REVISION

# Tables whose entries are grouped by value type.
SCOPED = {"expressions.json", "named_constants.json"}


def _json(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _entry_count(file: str, document: dict[str, Any]) -> int:
    entries = document["entries"]
    if file in SCOPED:
        return sum(len(scope) for scope in entries.values())
    return len(entries)


def render(documents: dict[str, dict[str, Any]], source_sha256: dict[str, str]) -> dict[str, bytes]:
    """File name -> bytes for every document plus manifest.json."""

    files = {
        file: {"entry_count": _entry_count(file, document)} for file, document in documents.items()
    }

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "source_revision": REVISION,
        "generator_version": GENERATOR_VERSION,
        "source_sha256": source_sha256,
        "files": files,
    }

    return {
        **{file: _json(document) for file, document in sorted(documents.items())},
        "manifest.json": _json(manifest),
    }
