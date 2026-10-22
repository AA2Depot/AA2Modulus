"""Prepare-rename and rename handlers."""

from __future__ import annotations

from lsprotocol import types
from pygls.exceptions import JsonRpcContentModified, JsonRpcException

from ....syntax import ast
from ...features.references import target_at
from ...features.rename import RenameError, StaleRename, prepare_rename, rename
from ..app import AA2LanguageServer


def _refused(error: RenameError) -> JsonRpcException:
    return JsonRpcException(message=str(error), code=types.LSPErrorCodes.RequestFailed.value)


def register(server: AA2LanguageServer) -> None:
    @server.feature(types.TEXT_DOCUMENT_PREPARE_RENAME)
    async def prepare(params: types.PrepareRenameParams) -> types.PrepareRenamePlaceholder | None:
        snapshot = await server.current_snapshot(params.text_document.uri)
        if snapshot is None:
            return None
        try:
            return prepare_rename(snapshot, params.position, server.encoding)
        except RenameError as error:
            raise _refused(error) from None

    @server.feature(types.TEXT_DOCUMENT_RENAME)
    async def rename_declaration(params: types.RenameParams) -> types.WorkspaceEdit | None:
        snapshot = await server.current_snapshot(params.text_document.uri)
        if snapshot is None:
            return None
        try:
            if prepare_rename(snapshot, params.position, server.encoding) is None:
                raise RenameError("There is no authored declaration to rename here")
            target = target_at(snapshot, params.position, server.encoding)
            assert target is not None
            scope = await server.scope(target, snapshot, params.work_done_token)
            plan = await server.offload(rename, scope, target, params.new_name, server.context)
        except StaleRename as error:
            raise JsonRpcContentModified(str(error)) from None
        except RenameError as error:
            raise _refused(error) from None
        edit = server.workspace_edit(plan, snapshot.document)
        if plan.files and isinstance(target.declaration, ast.SourceGlobal):
            server.window_show_message(
                types.ShowMessageParams(
                    types.MessageType.Warning,
                    f"Renamed global '{target.name}' to '{params.new_name}': its serialized "
                    f"variable name changes, and other modules on a card that read "
                    f"'{target.name}' still use the old name.",
                )
            )
        return edit
