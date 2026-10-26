"""Document synchronization and watched-file handlers."""

from __future__ import annotations

from lsprotocol import types

from ...protocol.positions import position_codec
from ..app import AA2LanguageServer


def register(server: AA2LanguageServer) -> None:
    @server.feature(types.WORKSPACE_DID_CHANGE_WATCHED_FILES)
    def watched_files(params: types.DidChangeWatchedFilesParams) -> None:
        server.index.changed(params.changes)
        # The server's own decompile output arrives as a creation; keep its findings.
        dropped = [
            server.drop_findings(change.uri)
            for change in params.changes
            if change.type != types.FileChangeType.Created
        ]
        if any(dropped):
            server.publish()

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(params: types.DidOpenTextDocumentParams) -> None:
        document = params.text_document
        server.enqueue(
            server.sources.open(document.uri, document.text, document.version, document.language_id)
        )

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(params: types.DidChangeTextDocumentParams) -> None:
        uri = params.text_document.uri
        document = server.sources.documents.get(uri)
        if document is None or params.text_document.version <= document.version:
            return
        text = document.text
        for change in params.content_changes:
            if isinstance(change, types.TextDocumentContentChangePartial):
                codec = position_codec(text, encoding=server.encoding)
                start = codec.offset(change.range.start)
                end = codec.offset(change.range.end)
                if end < start:
                    raise ValueError("document change range is reversed")
                text = text[:start] + change.text + text[end:]
            else:
                text = change.text
        server.drop_findings(uri)
        server.enqueue(server.sources.change(uri, text, params.text_document.version))

    @server.feature(types.TEXT_DOCUMENT_DID_SAVE, types.SaveOptions(include_text=False))
    def did_save(params: types.DidSaveTextDocumentParams) -> None:
        document = server.sources.documents.get(params.text_document.uri)
        if document is not None:
            server.enqueue(server.sources.invalidate(document.identity, uri=document.uri))

    @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
    async def did_close(params: types.DidCloseTextDocumentParams) -> None:
        server.tokens_served.pop(params.text_document.uri, None)
        server.drop_findings(params.text_document.uri)
        server.enqueue(server.sources.close(params.text_document.uri))
        server.publish()
        async with server.ready:
            server.ready.notify_all()
