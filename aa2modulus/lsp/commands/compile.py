"""Compile an open module and its imports, buffers before disk, with the strict compiler."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from pygls.exceptions import JsonRpcInvalidParams

from ...app.compile import CompileError, compile_source
from ...context.operation import SourceContext
from ...context.resolver import FileSourceResolver
from ...core.diagnostics import Diagnostic
from ..protocol.uris import identity_uri
from ..workspace.documents import DiskSignature, Document, disk_signature
from .arguments import file_argument, object_argument
from .findings import report_findings
from .results import CompileDocumentResult, diagnostic, failed, modified

if TYPE_CHECKING:
    from ..server.app import AA2LanguageServer

logger = logging.getLogger(__name__)


def _document(server: AA2LanguageServer, payload: Mapping[str, object]) -> Document:
    identifier = payload.get("textDocument")
    if not isinstance(identifier, Mapping):
        raise JsonRpcInvalidParams("textDocument must contain uri and version")
    uri = identifier.get("uri")
    version = identifier.get("version")
    if not isinstance(uri, str) or isinstance(version, bool) or not isinstance(version, int):
        raise JsonRpcInvalidParams("textDocument must contain a URI and integer version")
    document = server.sources.documents.get(uri)
    if document is None:
        raise failed(
            diagnostic(
                uri, "COMPILE_DOCUMENT_REQUIRED", "open the module document before compiling"
            )
        )
    if document.identity is None:
        raise failed(
            diagnostic(uri, "COMPILE_FILE_REQUIRED", "save the module as a .aa2m file first")
        )
    if document.is_library:
        raise failed(
            diagnostic(
                document.filename, "LIBRARY_COMPILE", "library files cannot be compiled as modules"
            )
        )
    if Path(document.identity).suffix != ".aa2m":
        raise failed(
            diagnostic(
                document.filename,
                "COMPILE_FILE_REQUIRED",
                "compilation requires a .aa2m source file",
            )
        )
    if document.version != version:
        raise modified(document.filename, "the module changed; retry compilation")
    return document


def _buffers(server: AA2LanguageServer) -> dict[str, Document]:
    """Open documents by identity; the newest revision wins for aliases, as in analysis."""

    return {
        document.identity: document
        for document in sorted(server.sources.documents.values(), key=lambda item: item.revision)
        if document.identity is not None
    }


@dataclass(slots=True)
class _Inputs:
    """Track the bounded inputs the strict compiler consumed: open buffers, then disk."""

    disk: FileSourceResolver
    buffers: Mapping[str, Document]
    texts: dict[str, str] = field(default_factory=dict)
    used: dict[str, Document] = field(default_factory=dict)
    signatures: dict[str, DiskSignature] = field(default_factory=dict)
    read_limits: dict[str, int] = field(default_factory=dict)
    stable: bool = True

    def resolve(self, path: str, *, importer: str | None) -> str:
        return self.disk.resolve(path, importer=importer)

    def read(self, identity: str, *, max_chars: int) -> str:
        buffer = self.buffers.get(identity)
        if buffer is not None:
            self.used[identity] = buffer
            # The prefix keeps the compiler's size diagnostic, as the disk reader does.
            text = self.texts[identity] = buffer.text[: max_chars + 1]
            return text
        before = disk_signature(identity)
        self.signatures[identity] = before
        self.read_limits[identity] = max_chars
        try:
            text = self.texts[identity] = self.disk.read(identity, max_chars=max_chars)
            return text
        finally:
            self.stable = self.stable and before == disk_signature(identity)

    def unchanged(self) -> bool:
        """Re-read each disk input; signatures miss same-size rewrites within
        one coarse filesystem timestamp tick (10 ms on WSL2 ext4).
        """

        for identity, limit in self.read_limits.items():
            try:
                if self.disk.read(identity, max_chars=limit) != self.texts[identity]:
                    return False
            except (OSError, UnicodeError):
                return False
        return True


@dataclass(frozen=True, slots=True)
class _Compilation:
    inputs: _Inputs
    data: bytes | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


def _compile(
    document: Document, buffers: Mapping[str, Document], context: SourceContext
) -> _Compilation:
    assert document.identity is not None
    inputs = _Inputs(FileSourceResolver(Path(document.identity).parent), buffers)
    inputs.texts[document.filename] = document.text
    operation = replace(
        context, filename=document.filename, import_base=None, source_resolver=inputs
    )
    try:
        data = compile_source(document.text, context=operation)
    except CompileError as error:
        return _Compilation(inputs, diagnostics=error.diagnostics)
    return _Compilation(inputs, data)


def _result(
    server: AA2LanguageServer,
    document: Document,
    inputs: _Inputs,
    findings: tuple[Diagnostic, ...],
    output: str | None = None,
) -> CompileDocumentResult:
    """Report a completed compile; ``output`` is the committed file, if any."""

    uri_for = partial(server.sources.uri_for, root=document)
    counts = report_findings(server, "compile", document.uri, findings, inputs.texts, uri_for)
    result: CompileDocumentResult = {
        "compiled": output is not None,
        "errors": counts["errors"],
        "warnings": counts["warnings"],
        "unlocated": counts["unlocated"],
    }
    if output is not None:
        result["outputUri"] = identity_uri(output)
    return result


def _verify_inputs(server: AA2LanguageServer, document: Document, inputs: _Inputs) -> None:
    if server.sources.documents.get(document.uri) != document:
        raise modified(document.filename, "the module changed during compilation; retry")
    buffers = _buffers(server)
    for identity, buffer in inputs.used.items():
        if buffers.get(identity) != buffer:
            raise modified(buffer.filename, "an imported source changed during compilation; retry")
    if not inputs.stable or any(
        identity in buffers or disk_signature(identity) != signature
        for identity, signature in inputs.signatures.items()
    ):
        raise modified(document.filename, "a source file changed during compilation; retry")


def _verify_output(output: str, inputs: _Inputs) -> None:
    for source in inputs.texts:
        same_file = output == source
        if not same_file:
            with contextlib.suppress(OSError):
                same_file = Path(output).samefile(source)
        if same_file:
            raise failed(
                diagnostic(
                    output, "COMPILE_OUTPUT_SOURCE", "output must not overwrite a source file"
                )
            )


def _stage_output(output: Path, data: bytes, *, canceled: threading.Event | None = None) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
        # The event-loop callback handles the usual cancellation path. This
        # worker-side check also cleans up if server shutdown closes the loop
        # before that callback can run.
        if canceled is not None and canceled.is_set():
            staged.unlink(missing_ok=True)
    except BaseException:
        if descriptor != -1:
            os.close(descriptor)
        staged.unlink(missing_ok=True)
        raise
    return staged


def _discard_staged(future: asyncio.Future[Path]) -> None:
    """Clean canceled writes after their worker closes the file, including on Windows."""

    try:
        future.result().unlink(missing_ok=True)
    except (OSError, asyncio.CancelledError):
        logger.warning("Could not clean a canceled module output", exc_info=True)


async def compile_document(server: AA2LanguageServer, value: object) -> CompileDocumentResult:
    """Compile the open buffers and saved files of the import graph, then
    atomically commit only if every input is still current.
    """

    payload = object_argument(value)
    document = _document(server, payload)
    output = file_argument(payload, "outputUri")
    loop = asyncio.get_running_loop()
    compilation = await loop.run_in_executor(
        server.executor, _compile, document, _buffers(server), server.context
    )
    inputs = compilation.inputs
    _verify_inputs(server, document, inputs)
    if compilation.data is None:
        return _result(server, document, inputs, compilation.diagnostics)
    _verify_output(output, inputs)
    staged: Path | None = None
    canceled = threading.Event()
    try:
        write = loop.run_in_executor(
            server.executor,
            partial(_stage_output, Path(output), compilation.data, canceled=canceled),
        )
        try:
            staged = await asyncio.shield(write)
        except asyncio.CancelledError:
            canceled.set()
            write.add_done_callback(_discard_staged)
            if write.done():
                _discard_staged(write)
            raise
        unchanged = await loop.run_in_executor(server.executor, inputs.unchanged)
        if not unchanged:
            raise modified(
                document.filename, "a source file changed on disk during compilation; retry"
            )
        _verify_inputs(server, document, inputs)
        if file_argument(payload, "outputUri") != output:
            raise modified(output, "the output path changed during compilation; retry")
        _verify_output(output, inputs)
        staged.replace(output)
    except OSError as error:
        failure = diagnostic(output, "OUTPUT_WRITE_ERROR", f"could not write module: {error}")
        return _result(server, document, inputs, (failure,))
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return _result(server, document, inputs, (), output)
