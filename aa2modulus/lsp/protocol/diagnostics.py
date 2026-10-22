"""Aggregate current compiler diagnostics by their primary editor document.

A published diagnostic with concrete fixes carries them in ``data`` (private to
this server) together with the document version they were computed for, so a
later ``textDocument/codeAction`` request applies them without re-analysis and
refuses them once the document has changed.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lsprotocol import types

from ...core.diagnostics import Diagnostic, SourceFix
from ...core.locations import RelatedLocation, SourceSpan
from ..workspace.documents import Snapshot, SourceWorkspace
from .positions import position_codec


def with_details(headline: str, diagnostic: Diagnostic) -> str:
    """Append a diagnostic's unlocated notes and help as extra message lines."""

    lines = [headline]
    lines.extend(f"note: {note}" for note in diagnostic.notes)
    if diagnostic.help is not None:
        lines.append(f"help: {diagnostic.help}")
    return "\n".join(lines)


def diagnostic_uris(snapshot: Snapshot, workspace: SourceWorkspace) -> frozenset[str]:
    """The documents ``snapshot`` publishes diagnostics under."""

    return frozenset(
        workspace.uri_for(diagnostic.filename, root=snapshot.document)
        for diagnostic in snapshot.analysis.result.diagnostics
    )


def aggregate_diagnostics(
    snapshots: Iterable[Snapshot], workspace: SourceWorkspace, encoding: str
) -> dict[str, list[types.Diagnostic]]:
    """LSP diagnostics per URI, each finding once with its related notes merged."""

    grouped: dict[
        str, dict[Diagnostic, tuple[Snapshot, list[tuple[RelatedLocation, Snapshot]]]]
    ] = {}
    for snapshot in snapshots:
        for diagnostic in snapshot.analysis.result.diagnostics:
            uri = workspace.uri_for(diagnostic.filename, root=snapshot.document)
            entries = grouped.setdefault(uri, {})
            if diagnostic not in entries:
                entries[diagnostic] = snapshot, []
            notes = entries[diagnostic][1]
            for note in diagnostic.related:
                uri = workspace.uri_for(note.span.filename, root=snapshot.document)
                if not any(
                    previous == note
                    and workspace.uri_for(previous.span.filename, root=owner.document) == uri
                    for previous, owner in notes
                ):
                    notes.append((note, snapshot))

    result = {}
    severity = {
        "error": types.DiagnosticSeverity.Error,
        "warning": types.DiagnosticSeverity.Warning,
        "info": types.DiagnosticSeverity.Information,
    }
    for uri, entries in grouped.items():
        converted = []
        document = workspace.documents.get(uri)
        version = document.version if document is not None else None
        for diagnostic, (snapshot, notes) in entries.items():
            span = diagnostic.source_span or SourceSpan(
                diagnostic.filename, diagnostic.line, diagnostic.column
            )
            related = [
                types.DiagnosticRelatedInformation(
                    types.Location(
                        workspace.uri_for(note.span.filename, root=owner.document),
                        position_codec(
                            owner.texts.get(note.span.filename, ""), encoding=encoding
                        ).range(note.span),
                    ),
                    note.message,
                )
                for note, owner in notes
            ]
            converted.append(
                types.Diagnostic(
                    range=position_codec(
                        snapshot.texts.get(span.filename, ""), encoding=encoding
                    ).range(span),
                    message=with_details(diagnostic.message, diagnostic),
                    severity=severity[diagnostic.severity],
                    code=diagnostic.code,
                    source="aa2modulus",
                    related_information=related or None,
                    data=_fix_data(diagnostic.fixes, snapshot, span.filename, version, encoding),
                )
            )
        result[uri] = converted
    return result


def _fix_data(
    fixes: tuple[SourceFix, ...],
    snapshot: Snapshot,
    filename: str,
    version: int | None,
    encoding: str,
) -> dict[str, Any] | None:
    """Fix edits in the published document's coordinates; only open documents get them."""

    usable = [fix for fix in fixes if fix.span.filename == filename]
    if version is None or not usable:
        return None
    codec = position_codec(snapshot.texts.get(filename, ""), encoding=encoding)
    return {
        "aa2modulus": {
            "version": version,
            "fixes": [
                {
                    "title": fix.title,
                    "range": _range_json(codec.range(fix.span)),
                    "newText": fix.replacement,
                }
                for fix in usable
            ],
        }
    }


def _range_json(range_: types.Range) -> dict[str, dict[str, int]]:
    return {
        "start": {"line": range_.start.line, "character": range_.start.character},
        "end": {"line": range_.end.line, "character": range_.end.character},
    }


def _fixes(diagnostic: types.Diagnostic, version: int) -> list[tuple[str, types.TextEdit]]:
    """The published fixes of one client-echoed diagnostic, if still current."""

    data = diagnostic.data
    entry = data.get("aa2modulus") if isinstance(data, dict) else None
    if not isinstance(entry, dict) or entry.get("version") != version:
        return []
    result = []
    for item in entry.get("fixes") or ():
        try:
            start, end = item["range"]["start"], item["range"]["end"]
            edit = types.TextEdit(
                types.Range(
                    types.Position(int(start["line"]), int(start["character"])),
                    types.Position(int(end["line"]), int(end["character"])),
                ),
                str(item["newText"]),
            )
            result.append((str(item["title"]), edit))
        except (KeyError, TypeError, ValueError):
            continue
    return result


def quick_fixes(
    uri: str,
    version: int,
    diagnostics: Iterable[types.Diagnostic],
    *,
    document_changes: bool,
) -> list[types.CodeAction]:
    """``quickfix`` actions for the echoed diagnostics; a lone fix is preferred."""

    actions = []
    for diagnostic in diagnostics:
        fixes = _fixes(diagnostic, version)
        for title, edit in fixes:
            workspace_edit = (
                types.WorkspaceEdit(
                    document_changes=[
                        types.TextDocumentEdit(
                            types.OptionalVersionedTextDocumentIdentifier(uri=uri, version=version),
                            [edit],
                        )
                    ]
                )
                if document_changes
                else types.WorkspaceEdit(changes={uri: [edit]})
            )
            actions.append(
                types.CodeAction(
                    title,
                    kind=types.CodeActionKind.QuickFix,
                    diagnostics=[diagnostic],
                    is_preferred=len(fixes) == 1 or None,
                    edit=workspace_edit,
                )
            )
    return actions
