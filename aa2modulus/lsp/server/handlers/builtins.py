"""Built-in pages over ``workspace/textDocumentContent`` and the built-in list."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from lsprotocol import types

from ....app.editor_catalog.document import DOCS_WEBSITE
from ....app.editor_catalog.pages import page_text
from ....app.editor_catalog.search import search
from ...documentation.builtins import builtin_symbol
from ..app import AA2LanguageServer

SYMBOL_LIMIT = 200


def register(server: AA2LanguageServer) -> None:
    documentation = server.documentation

    @server.feature(types.WORKSPACE_TEXT_DOCUMENT_CONTENT)
    async def content(params: types.TextDocumentContentParams) -> types.TextDocumentContentResult:
        entries = await server.offload(documentation.entries, server.context)
        path = unquote(urlsplit(params.uri).path)
        return types.TextDocumentContentResult(page_text(entries, path, website=DOCS_WEBSITE))

    @server.feature(types.WORKSPACE_SYMBOL)
    async def symbols(params: types.WorkspaceSymbolParams) -> list[types.WorkspaceSymbol]:
        if not documentation.enabled:
            return []
        entries = await server.offload(documentation.entries, server.context)
        found = search(list(entries.values()), params.query)
        return [builtin_symbol(entry) for entry in found[:SYMBOL_LIMIT]]
