"""Discard analysis superseded while the bounded compiler worker is running."""

from __future__ import annotations

import asyncio
import threading

from lsprotocol import types

from aa2modulus.lsp.server import worker
from aa2modulus.lsp.server.run import create_server


def test_running_analysis_cannot_publish_an_older_buffer_or_dependency(monkeypatch, tmp_path):
    original = worker.analyze_document
    started = threading.Event()
    release = threading.Event()
    root_uri = (tmp_path / "root.aa2m").as_uri()
    library_uri = (tmp_path / "lib.aa2mi").as_uri()

    def delayed(document, context, overlays):
        if document.uri == root_uri and document.version == 1:
            started.set()
            assert release.wait(timeout=5)
        return original(document, context, overlays)

    monkeypatch.setattr(worker, "analyze_document", delayed)

    async def session():
        server = create_server()
        publications = []
        monkeypatch.setattr(server, "text_document_publish_diagnostics", publications.append)
        server.start_workers()
        try:
            server.enqueue(server.sources.open(root_uri, 'module "old" { @ }', 1))
            assert await asyncio.to_thread(started.wait, 3)
            server.enqueue(
                server.sources.open(
                    library_uri, 'macro emit { Notification("buffer"); }', 1, "aa2mi"
                )
            )
            source = 'import "lib.aa2mi"; module "new" { trigger "T" { emit(); } }'
            server.enqueue(server.sources.change(root_uri, source, 2))
            release.set()
            snapshot = await asyncio.wait_for(server.current_snapshot(root_uri), timeout=5)
            assert snapshot.document.version == 2
            assert snapshot.analysis.module.name == "new"
            assert (
                snapshot.analysis.module.triggers[0]
                .gui_actions[0]
                .action.parameters[0]
                .constant.value
                == "buffer"
            )
            assert all(not item.diagnostics for item in publications)
            assert all(
                item.version != 1
                for item in publications
                if item.uri == root_uri and item.diagnostics
            )
        finally:
            release.set()
            await server.stop_workers()

    asyncio.run(session())


def test_first_completion_waits_for_running_analysis_without_replacing_its_snapshot(
    monkeypatch, tmp_path
):
    original = worker.analyze_document
    started = threading.Event()
    release = threading.Event()
    analyses = []
    uri = (tmp_path / "completion.aa2m").as_uri()
    source = 'module "M" { trigger "T" { if (Globals.) {} } }'
    offset = source.index("Globals.") + len("Globals.")

    def delayed(document, context, overlays):
        analyses.append(document.version)
        if len(analyses) == 1:
            started.set()
            assert release.wait(timeout=5)
        return original(document, context, overlays)

    monkeypatch.setattr(worker, "analyze_document", delayed)

    async def session():
        server = create_server()
        monkeypatch.setattr(server, "text_document_publish_diagnostics", lambda params: None)
        server.start_workers()
        try:
            server.enqueue(server.sources.open(uri, source, 1))
            assert await asyncio.to_thread(started.wait, 3)
            handler = server.protocol.fm.features[types.TEXT_DOCUMENT_COMPLETION]
            request = asyncio.create_task(
                handler(
                    types.CompletionParams(
                        text_document=types.TextDocumentIdentifier(uri),
                        position=types.Position(0, offset),
                    )
                )
            )
            # The request enters current_snapshot while its exact buffer is
            # already being analyzed, without a second request to prime it.
            await asyncio.sleep(0)
            release.set()
            items = await asyncio.wait_for(request, 5)
            assert "Globals.CurrentDay" in {item.label for item in items}
            assert analyses == [1]
        finally:
            release.set()
            await server.stop_workers()

    asyncio.run(session())
