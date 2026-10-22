"""Decompile a saved module file into recovered source."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...app.decompile import decompile_module, trailing_bytes_diagnostic
from ...binary.reader import DecodeError, ReaderLimits
from ...context.operation import SourceContext
from ...core.diagnostics import binary_diagnostic
from ...decompile.format.text import FormatError
from .arguments import file_argument, object_argument
from .locator import Locator, command_diagnostics
from .results import DecompileModuleResult, diagnostic, failed

if TYPE_CHECKING:
    from ..server.app import AA2LanguageServer

# Diagnostics located in decompiled text use this name until it becomes a document.
_RECOVERED = "<decompiled>"


def _decompile_file(identity: str, context: SourceContext, encoding: str) -> DecompileModuleResult:
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
    locator = Locator({_RECOVERED: result.source}, encoding)
    return {
        "source": result.source,
        "diagnostics": command_diagnostics(diagnostics, locator=locator),
    }


async def decompile_module_file(server: AA2LanguageServer, value: object) -> DecompileModuleResult:
    identity = file_argument(object_argument(value), "inputUri")
    return await asyncio.get_running_loop().run_in_executor(
        server.executor, _decompile_file, identity, server.context, server.encoding
    )
