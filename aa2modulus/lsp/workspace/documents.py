"""Versioned source overlays and dependency ownership for one editor session."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType

from ...context.operation import SourceContext
from ...context.resolver import FileSourceResolver
from ...pipeline.analysis import SourceAnalysis, analyze_source
from ...pipeline.authoring import SourceAuthoring, analyze_authoring
from ..protocol.uris import file_identity, identity_uri

type DiskSignature = tuple[int, int, int] | None


def disk_signature(identity: str) -> DiskSignature:
    try:
        stat = Path(identity).stat()
        return stat.st_mtime_ns, stat.st_size, stat.st_ino
    except OSError:
        return None


def read_disk(identity: str) -> tuple[str, DiskSignature] | None:
    """Read a closed file the way an editor would, with its signature at read time."""

    before = disk_signature(identity)
    try:
        with Path(identity).open(encoding="utf-8", newline="") as stream:
            text = stream.read()
    except (OSError, UnicodeDecodeError):
        return None
    # A write during the read changes the signature, so the next poll re-reads.
    return (text, before) if before is not None else None


@dataclass(frozen=True, slots=True)
class Document:
    uri: str
    text: str
    version: int
    identity: str | None
    revision: int
    language_id: str = "aa2m"

    @property
    def filename(self) -> str:
        return self.identity or self.uri

    @property
    def is_library(self) -> bool:
        return Path(self.identity or self.uri).suffix == ".aa2mi" or self.language_id == "aa2mi"


@dataclass(slots=True)
class OverlayResolver:
    """Use immutable editor inputs before the compiler's existing disk reader."""

    disk: FileSourceResolver
    overlays: Mapping[str, str]
    texts: dict[str, str] = field(default_factory=dict)
    signatures: dict[str, DiskSignature] = field(default_factory=dict)
    stable: bool = True

    def resolve(self, path: str, *, importer: str | None) -> str:
        return self.disk.resolve(path, importer=importer)

    def read(self, identity: str, *, max_chars: int) -> str:
        if identity in self.overlays:
            text = self.overlays[identity][: max_chars + 1]
        else:
            before = disk_signature(identity)
            self.signatures.setdefault(identity, before)
            text = self.disk.read(identity, max_chars=max_chars)
            self.stable = (
                self.stable
                and self.signatures[identity] == before
                and before == disk_signature(identity)
            )
        self.texts[identity] = text
        return text


@dataclass(frozen=True, slots=True)
class Snapshot:
    document: Document
    analysis: SourceAnalysis
    texts: Mapping[str, str]
    signatures: Mapping[str, DiskSignature]
    stable: bool = True
    authoring: SourceAuthoring = field(default_factory=SourceAuthoring)


def analyze_document(
    document: Document, context: SourceContext, overlays: Mapping[str, str]
) -> Snapshot:
    resolver = (
        OverlayResolver(FileSourceResolver(Path(document.identity).parent), overlays)
        if document.identity is not None
        else None
    )
    operation = replace(context, filename=document.filename, source_resolver=resolver)
    analysis = analyze_source(
        document.text,
        context=operation,
        source_kind="library" if document.is_library else "module",
    )
    authoring = analyze_authoring(
        document.text,
        operation,
        analysis=analysis,
        source_kind="library" if document.is_library else "module",
    )
    texts = {document.filename: document.text}
    if resolver is not None:
        texts.update(resolver.texts)
    return Snapshot(
        document,
        analysis,
        MappingProxyType(texts),
        MappingProxyType(resolver.signatures if resolver is not None else {}),
        resolver.stable if resolver is not None else True,
        authoring,
    )


class SourceWorkspace:
    """Keep open roots and their dependency sets without scanning directories.

    ``documents`` are editor buffers. A closed file stays a root in ``retained``,
    re-read from disk, so its diagnostics persist until the file is reopened,
    deleted or unreadable; ``snapshots`` holds the analysis of both kinds.
    """

    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.retained: dict[str, Document] = {}
        self.snapshots: dict[str, Snapshot] = {}
        self.dependencies: dict[str, frozenset[str]] = {}
        self.signatures: dict[str, DiskSignature] = {}
        self.revision = 0

    def overlays(self) -> dict[str, str]:
        return {
            document.identity: document.text
            for document in sorted(self.documents.values(), key=lambda item: item.revision)
            if document.identity is not None
        }

    def root(self, uri: str) -> Document | None:
        """Return the open or retained document analyzed for ``uri``."""

        return self.documents.get(uri) or self.retained.get(uri)

    def invalidate(self, identity: str | None, *, uri: str | None = None) -> set[str]:
        roots = {
            key
            for key, document in (*self.retained.items(), *self.documents.items())
            if key == uri
            or (
                identity is not None
                and (document.identity == identity or identity in self.dependencies.get(key, ()))
            )
        }
        for root in roots:
            self.snapshots.pop(root, None)
        return roots

    def open(self, uri: str, text: str, version: int, language_id: str = "aa2m") -> set[str]:
        self.revision += 1
        identity = file_identity(uri)
        for key in [
            key
            for key, item in self.retained.items()
            if key == uri or (identity is not None and item.identity == identity)
        ]:
            del self.retained[key]
            self.snapshots.pop(key, None)
            self.dependencies.pop(key, None)
        self.documents[uri] = Document(uri, text, version, identity, self.revision, language_id)
        return self.invalidate(identity, uri=uri)

    def change(self, uri: str, text: str, version: int) -> set[str]:
        """Replace an open document's text; the sync handler drops stale versions first."""

        previous = self.documents.get(uri)
        if previous is None:
            return set()
        return self.open(uri, text, version, previous.language_id)

    def close(self, uri: str) -> set[str]:
        previous = self.documents.pop(uri, None)
        snapshot = self.snapshots.pop(uri, None)
        if previous is None:
            return set()
        self.revision += 1
        roots = self.invalidate(previous.identity)
        retained = self._retain(previous)
        if retained is None:
            self.dependencies.pop(uri, None)
            return roots
        if snapshot is not None and snapshot.document.text == retained.text:
            self.snapshots[uri] = replace(snapshot, document=retained)
            return roots
        return roots | {uri}

    def _retain(self, document: Document) -> Document | None:
        identity = document.identity
        if identity is None or any(item.identity == identity for item in self.documents.values()):
            return None
        read = read_disk(identity)
        if read is None:
            return None
        text, signature = read
        retained = Document(document.uri, text, 0, identity, self.revision, document.language_id)
        self.retained[document.uri] = retained
        self.signatures[identity] = signature
        return retained

    def _reload(self, identity: str) -> set[str]:
        changed = set()
        for uri, document in list(self.retained.items()):
            if document.identity != identity:
                continue
            changed.add(uri)
            self.snapshots.pop(uri, None)
            del self.retained[uri]
            if self._retain(document) is None:
                self.dependencies.pop(uri, None)
        return changed

    def accept(self, snapshot: Snapshot, revision: int) -> bool:
        document = self.root(snapshot.document.uri)
        if document != snapshot.document or revision != self.revision or not snapshot.stable:
            return False
        if any(disk_signature(key) != value for key, value in snapshot.signatures.items()):
            return False
        uri = document.uri
        observed = frozenset(
            edge.identity
            for edge in (*snapshot.analysis.dependencies, *snapshot.authoring.dependencies)
        )
        if not snapshot.analysis.result.is_valid:
            observed |= self.dependencies.get(uri, frozenset())
        self.dependencies[uri] = observed
        self.snapshots[uri] = snapshot
        for identity in observed:
            self.signatures.setdefault(
                identity,
                snapshot.signatures[identity]
                if identity in snapshot.signatures
                else disk_signature(identity),
            )
        return True

    def poll_disk(self) -> set[str]:
        watched = set().union(*self.dependencies.values()) if self.dependencies else set()
        watched |= {item.identity for item in self.retained.values() if item.identity}
        overlays = self.overlays()
        changed = set()
        for identity in watched - overlays.keys():
            signature = disk_signature(identity)
            if identity in self.signatures and self.signatures[identity] != signature:
                changed.update(self.invalidate(identity))
                changed.update(self._reload(identity))
            self.signatures[identity] = signature
        self.signatures = {key: value for key, value in self.signatures.items() if key in watched}
        if changed:
            self.revision += 1
        return changed

    def uri_for(self, filename: str, *, root: Document | None = None) -> str:
        if root is not None and root.filename == filename:
            return root.uri
        aliases = [item for item in self.documents.values() if item.filename == filename]
        if aliases:
            return max(aliases, key=lambda item: item.revision).uri
        if filename.startswith("untitled:"):
            return filename
        return identity_uri(filename)
