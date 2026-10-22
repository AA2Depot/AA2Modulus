"""Completion and signature help."""

from __future__ import annotations

from lsprotocol import types

from ...completion.dispatch import completions
from ...protocol.positions import position_codec
from ...signature.help import signature_help
from ..app import AA2LanguageServer


def register(server: AA2LanguageServer) -> None:
    @server.feature(
        types.TEXT_DOCUMENT_COMPLETION, types.CompletionOptions(trigger_characters=["."])
    )
    async def completion(params: types.CompletionParams) -> list[types.CompletionItem]:
        snapshot = await server.current_snapshot(params.text_document.uri)
        if snapshot is None:
            return []
        source = snapshot.document.text
        offset = position_codec(source, encoding=server.encoding).offset(params.position)
        return await server.offload_current(
            snapshot,
            [],
            completions,
            source,
            offset,
            snapshot.analysis.context,
            encoding=server.encoding,
            analysis=snapshot.analysis,
            authoring=snapshot.authoring,
            texts=snapshot.texts,
            snippet_support=server.snippet_support,
        )

    @server.feature(
        types.TEXT_DOCUMENT_SIGNATURE_HELP,
        types.SignatureHelpOptions(trigger_characters=["(", ","]),
    )
    async def signatures(params: types.SignatureHelpParams) -> types.SignatureHelp | None:
        snapshot = await server.current_snapshot(params.text_document.uri)
        if snapshot is None:
            return None
        source = snapshot.document.text
        offset = position_codec(source, encoding=server.encoding).offset(params.position)
        return await server.offload_current(
            snapshot,
            None,
            signature_help,
            source,
            offset,
            snapshot.analysis.context,
            analysis=snapshot.analysis,
            authoring=snapshot.authoring,
            texts=snapshot.texts,
        )
