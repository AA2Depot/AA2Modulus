"""The language server object: protocol class, shared state and request helpers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, cast

from lsprotocol import types
from pygls.exceptions import JsonRpcContentModified
from pygls.lsp.server import LanguageServer
from pygls.protocol import LanguageServerProtocol, lsp_method

from ...app.editor_manifest import BUILTIN_CATALOG, COMPLETION_SNIPPETS, server_features
from ...context.operation import SourceContext
from ...version import __version__
from ..documentation.builtins import SCHEME, BuiltinDocumentation
from ..features.references import Target
from ..features.rename import RenamePlan
from ..protocol.diagnostics import aggregate_diagnostics, diagnostic_uris, merged_diagnostics
from ..protocol.positions import position_codec
from ..protocol.uris import file_identity
from ..workspace.documents import Document, Snapshot, SourceWorkspace, read_disk
from ..workspace.index import WorkspaceIndex, analyze_closed, discover
from .worker import analyze_pending, poll

logger = logging.getLogger(__name__)


class AA2LanguageServerProtocol(LanguageServerProtocol):
    @lsp_method(types.INITIALIZE)
    def lsp_initialize(
        self, params: types.InitializeParams
    ) -> Generator[Any, Any, types.InitializeResult]:
        result = yield from super().lsp_initialize(params)
        server = cast(AA2LanguageServer, self._server)
        features = server_features(context=server.context)
        if server.documentation.enabled:
            # pygls fills no textDocumentContent option, so the scheme is declared here.
            workspace = result.capabilities.workspace or types.WorkspaceOptions()
            workspace.text_document_content = types.TextDocumentContentOptions([SCHEME])
            result.capabilities.workspace = workspace
            features[BUILTIN_CATALOG] = True
        if server.snippet_support:
            features[COMPLETION_SNIPPETS] = True
        result.capabilities.experimental = {"aa2modulus": features}
        return result


class AA2LanguageServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__(
            "aa2modulus",
            __version__,
            types.TextDocumentSyncKind.Incremental,
            protocol_cls=AA2LanguageServerProtocol,
        )
        self.sources = SourceWorkspace()
        self.context = SourceContext.create()
        self.documentation = BuiltinDocumentation(self.context.metadata)
        self.index = WorkspaceIndex()
        self.snippet_support = False
        self.document_changes = False
        self.watch_files = False
        self.token_refresh = False
        self.show_document = False
        # The document each open URI's last semantic tokens came from; a new
        # analysis of that same document (an import changed) needs a refresh.
        self.tokens_served: dict[str, Document] = {}
        self.encoding = "utf-16"
        self.pending: dict[str, None] = {}
        self.analyzing: set[str] = set()
        self.failed: set[str] = set()
        # Last (version, diagnostics) sent per URI, and the URIs each root's snapshot sent to.
        self.published: dict[str, tuple[int | None, list[types.Diagnostic]]] = {}
        self.contributions: dict[str, frozenset[str]] = {}
        # Located findings of the last completed command run, keyed by compile
        # root or decompile output URI, then by the URI they are published on.
        self.command_findings: dict[str, dict[str, list[types.Diagnostic]]] = {}
        self.wake = asyncio.Event()
        self.ready = asyncio.Condition()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aa2m-analysis")
        # Closed workspace files are analyzed on their own thread, so a reference
        # or rename scan never queues ahead of completion and diagnostics.
        self.scan_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aa2m-workspace")
        self.tasks: list[asyncio.Task[None]] = []

    def start_workers(self) -> None:
        if not self.tasks:
            self.tasks = [
                asyncio.create_task(analyze_pending(self)),
                asyncio.create_task(poll(self)),
            ]

    def enqueue(self, roots: set[str]) -> None:
        for root in roots:
            self.pending[root] = None
            self.failed.discard(root)
        if roots:
            self.wake.set()
            self.publish()

    def publish(self) -> None:
        """Send the diagnostics that changed since the last publish.

        A root waiting for re-analysis keeps what it last sent until its new
        snapshot replaces it, so an edit never clears diagnostics in between.
        """

        snapshots = self.sources.snapshots
        diagnostics = merged_diagnostics(
            aggregate_diagnostics(snapshots.values(), self.sources, self.encoding),
            self.command_findings.values(),
        )
        waiting = {
            uri
            for uri in self.pending.keys() | self.analyzing
            if uri not in snapshots and self.sources.root(uri) is not None
        }
        self.contributions = {
            uri: diagnostic_uris(snapshot, self.sources) for uri, snapshot in snapshots.items()
        } | {uri: self.contributions[uri] for uri in waiting if uri in self.contributions}
        held = waiting.union(*(self.contributions.get(uri, ()) for uri in waiting))
        for uri in self.published.keys() | diagnostics.keys() | self.sources.documents.keys():
            document = self.sources.documents.get(uri)
            current = (
                document.version if document is not None else None,
                diagnostics.get(uri, []),
            )
            if uri in held or self.published.get(uri) == current:
                continue
            self.text_document_publish_diagnostics(
                types.PublishDiagnosticsParams(uri=uri, diagnostics=current[1], version=current[0])
            )
            if current[1] or document is not None:
                self.published[uri] = current
            else:
                self.published.pop(uri, None)

    def record_findings(self, key: str, findings: dict[str, list[types.Diagnostic]]) -> None:
        """Replace the located findings of command run ``key`` and publish them."""

        self.command_findings[key] = findings
        self.publish()

    def drop_findings(self, uri: str) -> bool:
        """Forget command findings on ``uri`` or another URI of its file; the
        caller publishes. Returns whether any were dropped.
        """

        identity = file_identity(uri)
        dropped = False
        for entry in self.command_findings.values():
            for target in [
                target
                for target in entry
                if target == uri or (identity is not None and file_identity(target) == identity)
            ]:
                del entry[target]
                dropped = True
        return dropped

    async def offload[**P, T](
        self, function: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs
    ) -> T:
        """Run ``function`` on the single analysis thread."""

        return await asyncio.get_running_loop().run_in_executor(
            self.executor, partial(function, *args, **kwargs)
        )

    async def offload_scan[**P, T](
        self, function: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs
    ) -> T:
        """Run a workspace scan step on the workspace thread."""

        return await asyncio.get_running_loop().run_in_executor(
            self.scan_executor, partial(function, *args, **kwargs)
        )

    async def offload_current[**P, T, S](
        self,
        snapshot: Snapshot,
        stale: S,
        function: Callable[P, T],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T | S:
        """Run ``function`` on the analysis thread; ``stale`` if ``snapshot`` was replaced."""

        result = await self.offload(function, *args, **kwargs)
        return result if self.sources.snapshots.get(snapshot.document.uri) is snapshot else stale

    async def current_snapshot(self, uri: str) -> Snapshot | None:
        async with self.ready:
            while uri in self.sources.documents:
                if uri in self.failed:
                    raise RuntimeError("Source analysis failed; see the server log")
                if snapshot := self.sources.snapshots.get(uri):
                    return snapshot
                if uri not in self.analyzing and uri not in self.pending:
                    self.pending[uri] = None
                    self.wake.set()
                await self.ready.wait()
        return None

    def workspace_folders(self) -> tuple[str, ...]:
        uris = [folder.uri for folder in self.workspace.folders.values()]
        if not uris and self.workspace.root_uri:
            uris = [self.workspace.root_uri]
        return tuple(sorted({identity for uri in uris if (identity := file_identity(uri))}))

    async def scope(
        self, target: Target, current: Snapshot, token: types.ProgressToken | None = None
    ) -> list[Snapshot]:
        """Analyses that can use ``target``: its file alone, or every workspace source.

        Open documents contribute their current snapshots; closed workspace files
        are analyzed from disk with open buffers overriding their imports.
        """

        snapshots = [current]
        if not target.workspace_wide:
            return snapshots
        for uri in list(self.sources.documents):
            if uri == current.document.uri:
                continue
            try:
                snapshot = await self.current_snapshot(uri)
            except RuntimeError:
                continue
            if snapshot is not None:
                snapshots.append(snapshot)
        folders = self.workspace_folders()
        if not folders:
            return snapshots
        if self.index.needs_discovery(folders):
            files, truncated = await self.offload_scan(discover, folders, cap=self.index.cap)
            if self.index.discovered(folders, files, truncated):
                self.window_show_message(
                    types.ShowMessageParams(
                        types.MessageType.Warning,
                        f"aa2modulus: references and rename read only the first "
                        f"{self.index.cap} workspace source files",
                    )
                )
        overlays = self.sources.overlays()
        open_files = {item.identity for item in self.sources.documents.values() if item.identity}
        stale = []
        for identity in self.index.files or ():
            if identity in open_files:
                continue
            if (snapshot := self.index.cached(identity, overlays)) is not None:
                snapshots.append(snapshot)
            else:
                stale.append(identity)
        if stale and token is not None:
            self.work_done_progress.begin(
                token, types.WorkDoneProgressBegin("Reading workspace sources", percentage=0)
            )
        try:
            for count, identity in enumerate(stale, 1):
                try:
                    result = await self.offload_scan(
                        analyze_closed, identity, self.context, overlays
                    )
                except Exception:  # one failing file must not fail the workspace scan
                    logger.exception("Source analysis failed for %s", identity)
                    continue
                if result is not None:
                    self.index.store(identity, *result)
                    snapshots.append(result[0])
                if token is not None and count % 20 == 0:
                    self.work_done_progress.report(
                        token, types.WorkDoneProgressReport(percentage=count * 100 // len(stale))
                    )
        finally:
            if stale and token is not None:
                self.work_done_progress.end(token, types.WorkDoneProgressEnd())
                self.work_done_progress.tokens.pop(token, None)
        return snapshots

    def workspace_edit(self, plan: RenamePlan, root: Document) -> types.WorkspaceEdit:
        """Edits against the texts the plan read, refusing files changed since then."""

        changes: dict[str, list[types.TextEdit]] = {}
        document_changes: list[
            types.TextDocumentEdit | types.CreateFile | types.RenameFile | types.DeleteFile
        ] = []
        for filename, item in plan.files.items():
            uri = self.sources.uri_for(filename, root=root)
            document = self.sources.documents.get(uri)
            version = None
            current: str | None
            if document is not None:
                current = document.text
                version = document.version
            else:
                read = None if filename.startswith("untitled:") else read_disk(filename)
                current = read[0] if read is not None else None
            if current != item.text:
                raise JsonRpcContentModified(f"{filename} changed during the rename; try again")
            codec = position_codec(item.text, encoding=self.encoding)
            edits = [
                types.TextEdit(
                    types.Range(codec.position(change.start), codec.position(change.end)),
                    change.text,
                )
                for change in item.changes
            ]
            changes[uri] = edits
            document_changes.append(
                types.TextDocumentEdit(
                    types.OptionalVersionedTextDocumentIdentifier(uri=uri, version=version),
                    edits,
                )
            )
        if self.document_changes:
            return types.WorkspaceEdit(document_changes=document_changes)
        return types.WorkspaceEdit(changes=changes)

    async def stop_workers(self) -> None:
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.scan_executor.shutdown(wait=False, cancel_futures=True)
