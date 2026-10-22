"""Quick-fix code actions."""

from __future__ import annotations

from lsprotocol import types

from ...protocol.diagnostics import quick_fixes
from ..app import AA2LanguageServer


def register(server: AA2LanguageServer) -> None:
    @server.feature(
        types.TEXT_DOCUMENT_CODE_ACTION,
        types.CodeActionOptions(code_action_kinds=[types.CodeActionKind.QuickFix]),
    )
    def code_actions(params: types.CodeActionParams) -> list[types.CodeAction]:
        # Fixes come from the published diagnostics' data; nothing is re-analyzed.
        only = params.context.only
        document = server.sources.documents.get(params.text_document.uri)
        if document is None or (
            only and not any(types.CodeActionKind.QuickFix.value.startswith(kind) for kind in only)
        ):
            return []
        return quick_fixes(
            document.uri,
            document.version,
            params.context.diagnostics,
            document_changes=server.document_changes,
        )
