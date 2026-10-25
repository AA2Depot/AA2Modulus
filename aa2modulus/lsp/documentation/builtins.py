"""Built-in documentation targets, pages and workspace symbols."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lsprotocol import types

from ...app.editor_catalog.document import editor_catalog
from ...context.operation import SourceContext
from ...language.documentation import DocumentedMetadata, builtin_anchor, constant_ordinals
from ...language.values import SourceValue
from ...metadata.identities import NativeMetadata
from ...metadata.snapshot import MetadataSnapshot

SCHEME = "aa2m-builtin"
_SYMBOL_KINDS = {
    "action": types.SymbolKind.Function,
    "event": types.SymbolKind.Event,
    "expression": types.SymbolKind.Function,
    "named_constant": types.SymbolKind.Constant,
}


class BuiltinDocumentation:
    """Read-only built-in pages, ``aa2m-builtin:/<anchor>.md``, one per stable anchor.

    Targets exist only when ``enabled``: the client advertised
    ``workspace.textDocumentContent``, so it can open the server's pages.
    """

    def __init__(self, metadata: MetadataSnapshot, *, enabled: bool = False) -> None:
        entries: tuple[NativeMetadata, ...] = (
            *metadata.actions,
            *metadata.events,
            *metadata.expressions,
        )
        self._keys: dict[int, str] = {id(entry): builtin_anchor(entry) for entry in entries}
        for constant, ordinal in constant_ordinals(metadata.named_constants):
            self._keys[id(constant)] = builtin_anchor(constant, ordinal=ordinal)
        self.enabled = enabled
        self._entries: dict[str, dict[str, Any]] | None = None

    def anchor(self, metadata: DocumentedMetadata) -> str | None:
        key = self._keys.get(id(metadata))
        if key is None and isinstance(metadata, SourceValue):
            key = builtin_anchor(metadata)
        return key

    def location(self, metadata: DocumentedMetadata) -> types.Location | None:
        anchor = self.anchor(metadata)
        return page_location(anchor) if anchor is not None and self.enabled else None

    def entries(self, context: SourceContext) -> dict[str, dict[str, Any]]:
        """``editor-catalog`` entries by id, built on the first call.

        The build compiles every example, so the server makes the first call on
        its analysis thread.
        """

        if self._entries is None:
            document, _ = editor_catalog(context=context)
            self._entries = {entry["id"]: entry for entry in document["entries"]}
        return self._entries


def page_location(anchor: str) -> types.Location:
    start = types.Position(0, 0)
    return types.Location(f"{SCHEME}:/{anchor}.md", types.Range(start, start))


def builtin_symbol(entry: Mapping[str, Any]) -> types.WorkspaceSymbol:
    return types.WorkspaceSymbol(
        location=page_location(entry["id"]),
        name=entry["name"],
        kind=_SYMBOL_KINDS[entry["kind"]],
        container_name=entry["nativeName"],
    )
