"""Semantic tokens and inlay hints."""

from __future__ import annotations

from lsprotocol import types

from ...features.inlay_hints import inlay_hints
from ...features.semantic_tokens import LEGEND, semantic_tokens
from ..app import AA2LanguageServer


def register(server: AA2LanguageServer) -> None:
    @server.feature(types.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL, LEGEND)
    async def tokens(params: types.SemanticTokensParams) -> types.SemanticTokens | None:
        # Waiting for the current analysis means tokens never come from an older text.
        snapshot = await server.current_snapshot(params.text_document.uri)
        if snapshot is None:
            return None
        server.tokens_served[params.text_document.uri] = snapshot.document
        return semantic_tokens(snapshot, server.encoding)

    @server.feature(types.TEXT_DOCUMENT_INLAY_HINT)
    async def hints(params: types.InlayHintParams) -> list[types.InlayHint]:
        snapshot = await server.current_snapshot(params.text_document.uri)
        return inlay_hints(snapshot, params.range, server.encoding) if snapshot else []
