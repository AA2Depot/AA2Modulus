"""The analysis worker: debounced analysis of pending roots and disk polling."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..workspace.documents import analyze_document

if TYPE_CHECKING:
    from .app import AA2LanguageServer

logger = logging.getLogger(__name__)


async def analyze_pending(server: AA2LanguageServer) -> None:
    while True:
        await server.wake.wait()
        await asyncio.sleep(0.2)
        server.wake.clear()
        refresh = False
        while server.pending:
            uri = next(iter(server.pending))
            server.pending.pop(uri)
            document = server.sources.root(uri)
            if document is None:
                continue
            revision = server.sources.revision
            overlays = server.sources.overlays()
            server.analyzing.add(uri)
            try:
                snapshot = await server.offload(
                    analyze_document, document, server.context, overlays
                )
            except Exception:  # one failing document must not stop the analysis worker
                logger.exception("Source analysis failed for %s", uri)
                server.failed.add(uri)
            else:
                if server.sources.accept(snapshot, revision):
                    server.publish()
                    refresh |= server.tokens_served.get(uri) is snapshot.document
                elif server.sources.root(uri) is not None:
                    server.pending[uri] = None
            finally:
                server.analyzing.discard(uri)
            async with server.ready:
                server.ready.notify_all()
        if refresh and server.token_refresh:
            server.workspace_semantic_tokens_refresh(None)


async def poll(server: AA2LanguageServer) -> None:
    while True:
        await asyncio.sleep(1)
        server.enqueue(server.sources.poll_disk())
