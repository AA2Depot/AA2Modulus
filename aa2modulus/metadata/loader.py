"""Load the shipped registry snapshot."""

from __future__ import annotations

from pathlib import Path

from .registry import load_registry
from .snapshot import MetadataSnapshot, index_snapshot

REGISTRY_DIRECTORY = "registry"


def _default_metadata_directory() -> Path:
    """Return the package-owned metadata resource directory."""

    return Path(__file__).resolve().parent / REGISTRY_DIRECTORY


def load_metadata(directory: str | Path | None = None) -> MetadataSnapshot:
    """Load validated shipped metadata without reading the source checkout."""

    registry_directory = _default_metadata_directory() if directory is None else Path(directory)
    return index_snapshot(load_registry(registry_directory))
