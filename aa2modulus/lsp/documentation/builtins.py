"""Built-in documentation targets and description text."""

from __future__ import annotations

import logging
import re

from lsprotocol import types

from ...language.documentation import DocumentedMetadata, builtin_anchor, constant_ordinals
from ...language.values import SourceValue
from ...metadata.identities import NativeMetadata
from ...metadata.snapshot import MetadataSnapshot

logger = logging.getLogger(__name__)
_URI_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


class BuiltinDocumentation:
    """Definition targets for built-ins: one read-only page per stable anchor.

    The client supplies ``builtinDocumentationBaseUri`` (the VS Code extension
    uses ``aa2m-builtin:/``) and renders ``<base><anchor>.md`` from its own
    generated data; the server never reads a documentation file.
    """

    def __init__(
        self,
        metadata: MetadataSnapshot,
        base_uri: str | None = None,
    ) -> None:
        entries: tuple[NativeMetadata, ...] = (
            *metadata.actions,
            *metadata.events,
            *metadata.expressions,
        )
        self._keys: dict[int, str] = {id(entry): builtin_anchor(entry) for entry in entries}
        for constant, ordinal in constant_ordinals(metadata.named_constants):
            self._keys[id(constant)] = builtin_anchor(constant, ordinal=ordinal)
        self.base_uri: str | None = None
        self.configure(base_uri)

    def configure(self, base_uri: str | None) -> None:
        if base_uri is not None and _URI_SCHEME.match(base_uri) is None:
            logger.warning("builtinDocumentationBaseUri must be an absolute URI: %r", base_uri)
            base_uri = None
        self.base_uri = base_uri

    def anchor(self, metadata: DocumentedMetadata) -> str | None:
        key = self._keys.get(id(metadata))
        if key is None and isinstance(metadata, SourceValue):
            key = builtin_anchor(metadata)
        return key

    def location(self, metadata: DocumentedMetadata) -> types.Location | None:
        anchor = self.anchor(metadata)
        if anchor is None or self.base_uri is None:
            return None
        start = types.Position(0, 0)
        return types.Location(f"{self.base_uri}{anchor}.md", types.Range(start, start))
