"""Lazy discovery and cached analysis of closed workspace sources.

References and rename for a library declaration read every `.aa2m`/`.aa2mi`
file under the workspace folders. Discovery runs on the first such request and
again after folder changes or watched-file creations and deletions (on every
request when the client cannot watch files). A cached analysis is reused only
while its root and every input it read still match disk or the open buffers.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from lsprotocol import types

from ...context.operation import SourceContext
from ..protocol.uris import file_identity, identity_uri
from .documents import (
    DiskSignature,
    Document,
    Snapshot,
    analyze_document,
    disk_signature,
    read_disk,
)

SOURCE_SUFFIXES = frozenset({".aa2m", ".aa2mi"})
FILE_CAP = 2000
WATCH_PATTERN = "**/*.{aa2m,aa2mi}"


def discover(folders: Sequence[str], *, cap: int = FILE_CAP) -> tuple[tuple[str, ...], bool]:
    """Source file identities under ``folders``, skipping hidden entries; True if capped."""

    found: dict[str, None] = {}
    for folder in folders:
        for directory, names, files in os.walk(folder):
            names[:] = sorted(name for name in names if not name.startswith("."))
            for name in sorted(files):
                if name.startswith(".") or Path(name).suffix.lower() not in SOURCE_SUFFIXES:
                    continue
                try:
                    identity = str(Path(directory, name).resolve())
                except (OSError, RuntimeError, ValueError):
                    continue
                if identity in found:
                    continue
                if len(found) >= cap:
                    return tuple(found), True
                found[identity] = None
    return tuple(found), False


@dataclass(frozen=True, slots=True)
class _Entry:
    snapshot: Snapshot
    signature: DiskSignature


def _fresh(entry: _Entry, overlays: Mapping[str, str]) -> bool:
    snapshot = entry.snapshot
    identity = snapshot.document.filename
    if identity in overlays or disk_signature(identity) != entry.signature:
        return False
    for name, signature in snapshot.signatures.items():
        if name in overlays or disk_signature(name) != signature:
            return False
    # Inputs not read from disk came from buffers that must still hold the same text.
    return all(
        name == identity or name in snapshot.signatures or overlays.get(name) == text
        for name, text in snapshot.texts.items()
    )


def analyze_closed(
    identity: str, context: SourceContext, overlays: Mapping[str, str]
) -> tuple[Snapshot, DiskSignature] | None:
    """Analyze a closed file from disk, with open buffers overriding its imports."""

    read = read_disk(identity)
    if read is None:
        return None
    text, signature = read
    language = "aa2mi" if Path(identity).suffix.lower() == ".aa2mi" else "aa2m"
    document = Document(identity_uri(identity), text, 0, identity, 0, language)
    return analyze_document(document, context, overlays), signature


class WorkspaceIndex:
    """Discovered workspace files and their cached closed-file analyses."""

    def __init__(self, cap: int = FILE_CAP) -> None:
        self.cap = cap
        self.watching = False
        self.folders: tuple[str, ...] = ()
        self.files: tuple[str, ...] | None = None
        self.truncated = False
        self.entries: dict[str, _Entry] = {}

    def needs_discovery(self, folders: tuple[str, ...]) -> bool:
        return self.files is None or folders != self.folders or not self.watching

    def discovered(self, folders: tuple[str, ...], files: tuple[str, ...], truncated: bool) -> bool:
        """Record a discovery; True when the cap newly truncated it."""

        report = truncated and not (self.truncated and folders == self.folders)
        self.folders, self.files, self.truncated = folders, files, truncated
        kept = set(files)
        self.entries = {key: value for key, value in self.entries.items() if key in kept}
        return report

    def changed(self, events: Iterable[types.FileEvent]) -> None:
        for event in events:
            identity = file_identity(event.uri)
            if identity is None:
                continue
            self.entries.pop(identity, None)
            if event.type != types.FileChangeType.Changed:
                self.files = None

    def cached(self, identity: str, overlays: Mapping[str, str]) -> Snapshot | None:
        entry = self.entries.get(identity)
        if entry is None or not _fresh(entry, overlays):
            return None
        return entry.snapshot

    def store(self, identity: str, snapshot: Snapshot, signature: DiskSignature) -> None:
        self.entries[identity] = _Entry(snapshot, signature)
