"""Workspace analysis and text-edit helpers that act like an editor."""

from __future__ import annotations

from collections.abc import Iterable

from lsprotocol import types

from aa2modulus.context.operation import SourceContext
from aa2modulus.lsp.protocol.diagnostics import aggregate_diagnostics
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.workspace.documents import Snapshot, SourceWorkspace, analyze_document


def analyze_workspace(workspace: SourceWorkspace, uri: str, context: SourceContext):
    revision = workspace.revision
    snapshot = analyze_document(workspace.root(uri), context, workspace.overlays())
    assert workspace.accept(snapshot, revision)
    return snapshot


def open_document(
    source: str, context: SourceContext, uri: str = "untitled:Document", language_id: str = "aa2m"
) -> tuple[SourceWorkspace, Snapshot]:
    """Open ``source`` as version 1 in a new workspace and analyze it."""

    workspace = SourceWorkspace()
    workspace.open(uri, source, 1, language_id)
    return workspace, analyze_workspace(workspace, uri, context)


def published_diagnostics(
    workspace: SourceWorkspace, uri: str, context: SourceContext
) -> list[types.Diagnostic]:
    """Analyze ``uri`` and return the diagnostics the server would publish for it."""

    analyze_workspace(workspace, uri, context)
    published = aggregate_diagnostics(workspace.snapshots.values(), workspace, "utf-16")
    return published.get(uri, [])


def apply_text_edit(source: str, item) -> str:
    assert item.text_edit is not None
    codec = PositionCodec(source)
    start = codec.offset(item.text_edit.range.start)
    end = codec.offset(item.text_edit.range.end)
    return source[:start] + item.text_edit.new_text + source[end:]


def apply_edits(source: str, edits: Iterable[types.TextEdit]) -> str:
    """Apply non-overlapping text edits, last position first."""

    codec = PositionCodec(source)
    spans = sorted(
        ((codec.offset(edit.range.start), codec.offset(edit.range.end), edit) for edit in edits),
        key=lambda item: item[0],
        reverse=True,
    )
    for start, end, edit in spans:
        source = source[:start] + edit.new_text + source[end:]
    return source


def notification_text(snapshot: Snapshot) -> str:
    """The text of the first trigger's first ``Notification`` argument."""

    action = snapshot.analysis.module.triggers[0].gui_actions[0].action
    return action.parameters[0].constant.value
