"""Hover, definition, references, highlights, document links and symbols."""

from __future__ import annotations

from functools import partial

from lsprotocol import types

from ....app.editor_catalog.search import search
from ...documentation.builtins import builtin_symbol
from ...features import navigation
from ...features.references import document_highlights, reference_locations, target_at
from ..app import AA2LanguageServer

SYMBOL_LIMIT = 200


def register(server: AA2LanguageServer) -> None:
    @server.feature(types.TEXT_DOCUMENT_HOVER)
    async def hover(params: types.HoverParams) -> types.Hover | None:
        snapshot = await server.current_snapshot(params.text_document.uri)
        return navigation.hover(snapshot, params.position, server.encoding) if snapshot else None

    @server.feature(types.TEXT_DOCUMENT_DEFINITION)
    async def definition(params: types.DefinitionParams) -> list[types.Location]:
        snapshot = await server.current_snapshot(params.text_document.uri)
        return (
            navigation.definition(
                snapshot,
                params.position,
                server.encoding,
                server.sources,
                documentation=server.documentation,
            )
            if snapshot
            else []
        )

    @server.feature(types.TEXT_DOCUMENT_REFERENCES)
    async def references(params: types.ReferenceParams) -> list[types.Location]:
        snapshot = await server.current_snapshot(params.text_document.uri)
        target = target_at(snapshot, params.position, server.encoding) if snapshot else None
        if snapshot is None or target is None:
            return []
        scope = await server.scope(target, snapshot, params.work_done_token)
        return await server.offload(
            reference_locations,
            scope,
            target,
            server.encoding,
            partial(server.sources.uri_for, root=snapshot.document),
            include_declaration=params.context.include_declaration,
        )

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_HIGHLIGHT)
    async def highlights(params: types.DocumentHighlightParams) -> list[types.DocumentHighlight]:
        snapshot = await server.current_snapshot(params.text_document.uri)
        return document_highlights(snapshot, params.position, server.encoding) if snapshot else []

    @server.feature(
        types.TEXT_DOCUMENT_DOCUMENT_LINK, types.DocumentLinkOptions(resolve_provider=False)
    )
    async def links(params: types.DocumentLinkParams) -> list[types.DocumentLink]:
        snapshot = await server.current_snapshot(params.text_document.uri)
        return (
            navigation.document_links(snapshot, server.encoding, server.sources.uri_for)
            if snapshot
            else []
        )

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    async def symbols(params: types.DocumentSymbolParams) -> list[types.DocumentSymbol]:
        snapshot = await server.current_snapshot(params.text_document.uri)
        return navigation.document_symbols(snapshot, server.encoding) if snapshot else []

    @server.feature(types.WORKSPACE_SYMBOL)
    async def workspace_symbols(
        params: types.WorkspaceSymbolParams,
    ) -> list[types.WorkspaceSymbol]:
        snapshots = await server.workspace_snapshots(params.work_done_token)
        found = await server.offload(
            navigation.workspace_symbols, snapshots, params.query, encoding=server.encoding
        )
        found = found[:SYMBOL_LIMIT]
        if server.documentation.enabled:
            entries = await server.offload(server.documentation.entries, server.context)
            builtins = search(list(entries.values()), params.query)
            found += [builtin_symbol(entry) for entry in builtins[: SYMBOL_LIMIT - len(found)]]
        return found
