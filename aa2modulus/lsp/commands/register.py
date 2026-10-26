"""Register the module commands on the language server."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .compile import compile_document
from .decompile import decompile_module_file
from .results import (
    COMPILE_DOCUMENT,
    DECOMPILE_MODULE,
    CompileDocumentResult,
    DecompileModuleResult,
)

if TYPE_CHECKING:
    from ..server.app import AA2LanguageServer


def register_commands(server: AA2LanguageServer) -> None:
    # Any preserves the JSON object through Pygls/cattrs; each handler validates
    # the wire shape before using it. Server types stay out of runtime imports.
    @server.command(COMPILE_DOCUMENT)
    async def compile_(payload: Any) -> CompileDocumentResult:
        return await compile_document(server, payload)

    @server.command(DECOMPILE_MODULE)
    async def decompile(payload: Any) -> DecompileModuleResult:
        return await decompile_module_file(server, payload)
