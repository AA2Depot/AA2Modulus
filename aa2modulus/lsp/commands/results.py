"""Command names, wire result shapes and the failures commands raise."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from lsprotocol import types
from pygls.exceptions import JsonRpcContentModified, JsonRpcException

from ...core.diagnostics import Diagnostic, DiagnosticSeverity

PREPARE_COMPILE = "aa2modulus.prepareCompile"
COMPILE_DOCUMENT = "aa2modulus.compileDocument"
DECOMPILE_MODULE = "aa2modulus.decompileModule"


class CommandPosition(TypedDict):
    line: int
    character: int


class CommandRange(TypedDict):
    start: CommandPosition
    end: CommandPosition


class CommandRelated(TypedDict):
    uri: NotRequired[str]
    range: CommandRange
    message: str


class CommandDiagnostic(TypedDict):
    """One finding; ``range`` is present only when its text is known to the command."""

    severity: DiagnosticSeverity
    message: str
    code: str
    detail: str
    target: NotRequired[Literal["source", "recovered"]]
    uri: NotRequired[str]
    range: NotRequired[CommandRange]
    related: NotRequired[list[CommandRelated]]


class PrepareCompileResult(TypedDict):
    dependencies: list[str]
    diagnostics: list[CommandDiagnostic]


class CompileDocumentResult(TypedDict):
    compiled: bool
    diagnostics: list[CommandDiagnostic]


class DecompileModuleResult(TypedDict):
    source: str
    diagnostics: list[CommandDiagnostic]


def diagnostic(filename: str, code: str, message: str) -> Diagnostic:
    return Diagnostic(filename, 1, 1, "error", code, message)


def failed(diagnostic: Diagnostic) -> JsonRpcException:
    return JsonRpcException(message=str(diagnostic), code=types.LSPErrorCodes.RequestFailed.value)


def modified(filename: str, message: str) -> JsonRpcContentModified:
    return JsonRpcContentModified(str(diagnostic(filename, "COMPILE_SOURCE_CHANGED", message)))
