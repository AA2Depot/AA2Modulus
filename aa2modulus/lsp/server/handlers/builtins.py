"""Built-in pages over ``workspace/textDocumentContent``."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from lsprotocol import types

from ....app.editor_catalog.pages import page_text
from ....language.documentation import DOCS_WEBSITE
from ..app import AA2LanguageServer


def register(server: AA2LanguageServer) -> None:
    documentation = server.documentation

    @server.feature(types.WORKSPACE_TEXT_DOCUMENT_CONTENT)
    async def content(params: types.TextDocumentContentParams) -> types.TextDocumentContentResult:
        entries = await server.offload(documentation.entries, server.context)
        path = unquote(urlsplit(params.uri).path)
        return types.TextDocumentContentResult(page_text(entries, path, website=DOCS_WEBSITE))
