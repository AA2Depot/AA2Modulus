"""Command names, wire result shapes and the failures commands raise."""

from __future__ import annotations

from typing import NotRequired, TypedDict

from lsprotocol import types
from pygls.exceptions import JsonRpcContentModified, JsonRpcException

from ...core.diagnostics import Diagnostic, DiagnosticSeverity

COMPILE_DOCUMENT = "aa2modulus.compileDocument"
DECOMPILE_MODULE = "aa2modulus.decompileModule"


class CommandFinding(TypedDict):
    """A finding without a range; ``message`` is the CLI short line plus notes and help."""

    severity: DiagnosticSeverity
    code: str
    message: str


class CommandCounts(TypedDict):
    """Errors and warnings among every finding of a command, and the unlocated ones."""

    errors: int
    warnings: int
    unlocated: list[CommandFinding]


class CompileDocumentResult(CommandCounts):
    compiled: bool
    outputUri: NotRequired[str]


class DecompileModuleResult(CommandCounts):
    outputUri: str


def diagnostic(filename: str, code: str, message: str) -> Diagnostic:
    return Diagnostic(filename, 1, 1, "error", code, message)


def failed(diagnostic: Diagnostic) -> JsonRpcException:
    return JsonRpcException(message=str(diagnostic), code=types.LSPErrorCodes.RequestFailed.value)


def modified(filename: str, message: str) -> JsonRpcContentModified:
    return JsonRpcContentModified(str(diagnostic(filename, "COMPILE_SOURCE_CHANGED", message)))
