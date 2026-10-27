"""Load the shipped registry snapshot."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from .registry import load_registry
from .snapshot import MetadataSnapshot, index_snapshot

REGISTRY_DIRECTORY = "registry"

_shipped: MetadataSnapshot | None = None
_shipped_lock = Lock()


def _default_metadata_directory() -> Path:
    """Return the package-owned metadata resource directory."""

    return Path(__file__).resolve().parent / REGISTRY_DIRECTORY


def load_metadata(directory: str | Path | None = None) -> MetadataSnapshot:
    """Load validated shipped metadata without reading the source checkout.

    The shipped snapshot is immutable, so a process loads it once.
    """

    global _shipped
    if directory is not None:
        return index_snapshot(load_registry(Path(directory)))
    snapshot = _shipped
    if snapshot is None:
        with _shipped_lock:
            snapshot = _shipped
            if snapshot is None:
                snapshot = index_snapshot(load_registry(_default_metadata_directory()))
                _shipped = snapshot
    return snapshot
