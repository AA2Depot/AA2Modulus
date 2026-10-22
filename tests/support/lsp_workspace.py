"""Workspace analysis and text-edit helpers that act like an editor."""

from __future__ import annotations

from aa2modulus.context.operation import SourceContext
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.workspace.documents import SourceWorkspace, analyze_document


def analyze_workspace(workspace: SourceWorkspace, uri: str, context: SourceContext):
    revision = workspace.revision
    snapshot = analyze_document(workspace.root(uri), context, workspace.overlays())
    assert workspace.accept(snapshot, revision)
    return snapshot


def apply_text_edit(source: str, item) -> str:
    assert item.text_edit is not None
    codec = PositionCodec(source)
    start = codec.offset(item.text_edit.range.start)
    end = codec.offset(item.text_edit.range.end)
    return source[:start] + item.text_edit.new_text + source[end:]
