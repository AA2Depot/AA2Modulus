"""Compile a saved module document through the strict compiler."""

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
from ...semantics.binding.state import SourceBindingError
from ..workspace.documents import DiskSignature, Document, disk_signature
from .arguments import file_argument, object_argument
from .locator import command_diagnostics, source_locator
from .results import (
    CompileDocumentResult,
    PrepareCompileResult,
    diagnostic,
    failed,
    modified,
)

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
        raise modified(document.filename, "the module changed; save it and retry compilation")
    return document


async def prepare_compile(server: AA2LanguageServer, value: object) -> PrepareCompileResult:
    """Discover only the current import graph, including unsaved library inputs."""

    payload = object_argument(value)
    document = _document(server, payload)
    snapshot = await server.current_snapshot(document.uri)
    if snapshot is None or _document(server, payload) != document:
        raise modified(document.filename, "the module changed while discovering its imports")
    # Workspace dependencies deliberately retain earlier edges after failures for
    # invalidation. Saving and compilation must use this operation's actual edges.
    dependencies = list(
        dict.fromkeys(
            server.sources.uri_for(edge.identity, root=document)
            for edge in snapshot.analysis.dependencies
        )
    )
    failure = snapshot.analysis.failure
    discovery = (
        snapshot.analysis.result.diagnostics
        if failure is not None and not isinstance(failure, SourceBindingError)
        else ()
    )
    return {
        "dependencies": dependencies,
        "diagnostics": command_diagnostics(
            discovery, locator=source_locator(server, document, snapshot.texts)
        ),
    }


@dataclass(slots=True)
class _SavedFiles:
    """Track the exact bounded disk inputs consumed by the strict compiler."""

    disk: FileSourceResolver
    texts: dict[str, str] = field(default_factory=dict)
    signatures: dict[str, DiskSignature] = field(default_factory=dict)
    read_limits: dict[str, int] = field(default_factory=dict)
    stable: bool = True

    def resolve(self, path: str, *, importer: str | None) -> str:
        return self.disk.resolve(path, importer=importer)

    def read(self, identity: str, *, max_chars: int) -> str:
        before = disk_signature(identity)
        self.signatures[identity] = before
        self.read_limits[identity] = max_chars
        try:
            text = self.disk.read(identity, max_chars=max_chars)
            self.texts[identity] = text
            return text
        finally:
            self.stable = self.stable and before == disk_signature(identity)

    def unchanged(self) -> bool:
        """Re-read each consumed input; signatures miss same-size rewrites within
        one coarse filesystem timestamp tick (10 ms on WSL2 ext4).
        """

        for identity, text in self.texts.items():
            try:
                if self.disk.read(identity, max_chars=self.read_limits[identity]) != text:
                    return False
            except (OSError, UnicodeError):
                return False
        return True

    def matches(self, document: Document, text: str) -> bool:
        # Oversized inputs are intentionally read only up to the compiler limit
        # plus one. They can never produce output, but retain the size diagnostic
        # when the open buffer agrees with the bounded prefix.
        limit = self.read_limits[document.filename]
        return document.text[: len(text)] == text if len(text) > limit else document.text == text


@dataclass(frozen=True, slots=True)
class _Compilation:
    files: _SavedFiles
    data: bytes | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


def _compile_saved(document: Document, context: SourceContext) -> _Compilation:
    assert document.identity is not None
    files = _SavedFiles(FileSourceResolver(Path(document.identity).parent))
    operation = replace(
        context, filename=document.filename, import_base=None, source_resolver=files
    )
    try:
        source = files.read(
            document.identity,
            max_chars=min(
                operation.source_limits.max_source_chars,
                operation.source_limits.max_total_source_chars,
            ),
        )
        data = compile_source(source, context=operation)
    except CompileError as error:
        return _Compilation(files, diagnostics=error.diagnostics)
    except UnicodeError as error:
        return _Compilation(
            files,
            diagnostics=(
                diagnostic(
                    document.filename, "SOURCE_ENCODING", f"source is not valid UTF-8: {error}"
                ),
            ),
        )
    except OSError as error:
        return _Compilation(
            files,
            diagnostics=(
                diagnostic(
                    document.filename, "SOURCE_READ_ERROR", f"could not read source: {error}"
                ),
            ),
        )
    return _Compilation(files, data)


def _verify_inputs(
    server: AA2LanguageServer,
    document: Document,
    compilation: _Compilation,
    buffers: tuple[Document, ...],
) -> None:
    files = compilation.files
    if server.sources.documents.get(document.uri) != document:
        raise modified(
            document.filename, "the module changed during compilation; save it and retry"
        )
    if not files.stable or any(
        disk_signature(identity) != signature for identity, signature in files.signatures.items()
    ):
        raise modified(document.filename, "a source file changed on disk during compilation; retry")
    for buffer in (*buffers, *server.sources.documents.values()):
        if buffer.identity in files.texts and not files.matches(
            buffer, files.texts[buffer.identity]
        ):
            raise modified(buffer.filename, "save this source file before compiling the module")
    for buffer in buffers:
        if buffer.identity in files.signatures:
            current = server.sources.documents.get(buffer.uri)
            if current != buffer:
                raise modified(
                    buffer.filename, "an imported source changed during compilation; retry"
                )


def _verify_output(output: str, files: _SavedFiles) -> None:
    for source in files.signatures:
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
    """Compile saved source and atomically commit only still-current inputs."""

    payload = object_argument(value)
    document = _document(server, payload)
    output = file_argument(payload, "outputUri")
    buffers = tuple(server.sources.documents.values())
    loop = asyncio.get_running_loop()
    compilation = await loop.run_in_executor(
        server.executor, _compile_saved, document, server.context
    )
    _verify_inputs(server, document, compilation, buffers)
    if compilation.data is None:
        return {
            "compiled": False,
            "diagnostics": command_diagnostics(
                compilation.diagnostics,
                locator=source_locator(server, document, compilation.files.texts),
            ),
        }
    _verify_output(output, compilation.files)
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
        unchanged = await loop.run_in_executor(server.executor, compilation.files.unchanged)
        if not unchanged:
            raise modified(
                document.filename, "a source file changed on disk during compilation; retry"
            )
        _verify_inputs(server, document, compilation, buffers)
        if file_argument(payload, "outputUri") != output:
            raise modified(output, "the output path changed during compilation; retry")
        _verify_output(output, compilation.files)
        staged.replace(output)
    except OSError as error:
        return {
            "compiled": False,
            "diagnostics": command_diagnostics(
                (diagnostic(output, "OUTPUT_WRITE_ERROR", f"could not write module: {error}"),)
            ),
        }
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return {"compiled": True, "diagnostics": []}
