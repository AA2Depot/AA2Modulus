"""Initialization and shutdown handlers."""

from __future__ import annotations

from concurrent.futures import Future

from lsprotocol import types

from ...workspace.index import WATCH_PATTERN
from ..app import AA2LanguageServer


def register(server: AA2LanguageServer) -> None:
    @server.feature(types.INITIALIZE)
    def initialize(params: types.InitializeParams) -> None:
        encoding = server.workspace.position_encoding
        server.encoding = (
            encoding.value
            if isinstance(encoding, types.PositionEncodingKind)
            else encoding or "utf-16"
        )
        text_document = params.capabilities.text_document
        completion_options = text_document.completion if text_document else None
        item_options = completion_options.completion_item if completion_options else None
        server.snippet_support = bool(item_options and item_options.snippet_support)
        workspace = params.capabilities.workspace
        edit_options = workspace.workspace_edit if workspace else None
        server.document_changes = bool(edit_options and edit_options.document_changes)
        watched = workspace.did_change_watched_files if workspace else None
        server.watch_files = bool(watched and watched.dynamic_registration)
        tokens = workspace.semantic_tokens if workspace else None
        server.token_refresh = bool(tokens and tokens.refresh_support)
        server.documentation.enabled = bool(workspace and workspace.text_document_content)
        window = params.capabilities.window
        show_document = window.show_document if window else None
        server.show_document = bool(show_document and show_document.support)

    @server.feature(types.INITIALIZED)
    def initialized(params: types.InitializedParams) -> None:
        server.start_workers()
        if not server.watch_files:
            return
        registration = types.Registration(
            "aa2modulus-workspace-sources",
            types.WORKSPACE_DID_CHANGE_WATCHED_FILES,
            types.DidChangeWatchedFilesRegistrationOptions(
                [types.FileSystemWatcher(glob_pattern=WATCH_PATTERN)]
            ),
        )

        def registered(future: Future[None]) -> None:
            if not future.cancelled() and future.exception() is None:
                server.index.watching = True

        server.client_register_capability(
            types.RegistrationParams([registration])
        ).add_done_callback(registered)

    @server.feature(types.SHUTDOWN)
    async def shutdown(*args: object) -> None:
        await server.stop_workers()
