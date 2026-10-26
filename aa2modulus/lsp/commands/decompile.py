"""Decompile a saved module file into a new recovered source file beside it."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from lsprotocol import types
from pygls.exceptions import JsonRpcException

from ...app.decompile import decompile_module, trailing_bytes_diagnostic
from ...binary.reader import DecodeError, ReaderLimits
from ...context.operation import SourceContext
from ...core.diagnostics import Diagnostic, binary_diagnostic
from ...decompile.format.text import FormatError
from ..protocol.uris import identity_uri
from .arguments import file_argument, object_argument
from .findings import report_findings
from .results import DecompileModuleResult, diagnostic, failed

if TYPE_CHECKING:
    from ..server.app import AA2LanguageServer

logger = logging.getLogger(__name__)

# Diagnostics located in decompiled text use this name until its file is written.
_RECOVERED = "<decompiled>"
_LAST_SUFFIX = 100


@dataclass(frozen=True, slots=True)
class _Recovery:
    identity: str
    source: str
    diagnostics: tuple[Diagnostic, ...]


def _candidates(identity: str) -> Iterator[Path]:
    """``<input>.aa2m``, then ``<input>-2.aa2m`` up to ``-100``."""

    yield Path(f"{identity}.aa2m")
    for number in range(2, _LAST_SUFFIX + 1):
        yield Path(f"{identity}-{number}.aa2m")


def _write_source(identity: str, source: str, taken: frozenset[str]) -> str:
    """Create the first candidate that is neither on disk nor open; never overwrite."""

    for path in _candidates(identity):
        if str(path) in taken:
            continue
        created = False
        try:
            with path.open("x", encoding="utf-8", newline="") as stream:
                created = True
                stream.write(source)
        except FileExistsError:
            continue
        except (OSError, UnicodeError) as error:
            if created:
                path.unlink(missing_ok=True)
            raise failed(
                diagnostic(
                    str(path), "DECOMPILE_WRITE_ERROR", f"could not write recovered source: {error}"
                )
            ) from error
        return str(path)
    raise failed(
        diagnostic(
            identity,
            "DECOMPILE_OUTPUT_EXISTS",
            f"every recovered source name up to {identity}-{_LAST_SUFFIX}.aa2m is taken",
        )
    )


def _decompile_file(identity: str, context: SourceContext, taken: frozenset[str]) -> _Recovery:
    try:
        with Path(identity).open("rb") as stream:
            data = stream.read(ReaderLimits().max_input_bytes + 1)
        result = decompile_module(
            data, context=replace(context, filename=identity), source_filename=_RECOVERED
        )
    except DecodeError as error:
        raise failed(binary_diagnostic(identity, error)) from error
    except (OSError, FormatError) as error:
        raise failed(
            diagnostic(identity, "DECOMPILE_ERROR", f"could not decompile module: {error}")
        ) from error
    diagnostics = result.diagnostics
    if trailing := result.decoded.trailing_bytes:
        diagnostics = (*diagnostics, trailing_bytes_diagnostic(identity, trailing))
    return _Recovery(_write_source(identity, result.source, taken), result.source, diagnostics)


async def _show(server: AA2LanguageServer, uri: str) -> None:
    """Ask the client to open ``uri``; a refusal is logged, never a command failure."""

    try:
        shown = await server.window_show_document_async(
            types.ShowDocumentParams(uri, take_focus=True)
        )
    except JsonRpcException:
        logger.warning("The client could not show %s", uri, exc_info=True)
        return
    if not shown.success:
        logger.warning("The client did not show %s", uri)


async def decompile_module_file(server: AA2LanguageServer, value: object) -> DecompileModuleResult:
    identity = file_argument(object_argument(value), "inputUri")
    taken = frozenset(
        document.identity
        for document in server.sources.documents.values()
        if document.identity is not None
    )
    recovery = await asyncio.get_running_loop().run_in_executor(
        server.executor, _decompile_file, identity, server.context, taken
    )
    output = identity_uri(recovery.identity)
    counts = report_findings(
        server,
        "decompile",
        output,
        recovery.diagnostics,
        {_RECOVERED: recovery.source},
        lambda _filename: output,
    )
    if server.show_document:
        await _show(server, output)
    return {"outputUri": output, **counts}
