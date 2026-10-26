"""Report a command's findings: counts, unlocated results, log lines and published diagnostics."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Literal

from lsprotocol import types

from ...core.diagnostics import Diagnostic
from ..protocol.diagnostics import lsp_diagnostic, with_details
from .results import CommandCounts

if TYPE_CHECKING:
    from ..server.app import AA2LanguageServer

_MESSAGE_TYPE = {
    "error": types.MessageType.Error,
    "warning": types.MessageType.Warning,
    "info": types.MessageType.Info,
}


def report_findings(
    server: AA2LanguageServer,
    command: Literal["compile", "decompile"],
    key: str,
    findings: Iterable[Diagnostic],
    texts: Mapping[str, str],
    uri_for: Callable[[str], str],
) -> CommandCounts:
    """Log every finding, count them, and publish those located in ``texts``.

    The published findings replace the previous ones of command run ``key``.
    """

    counts: CommandCounts = {"errors": 0, "warnings": 0, "unlocated": []}
    located: dict[str, list[types.Diagnostic]] = {}
    for item in findings:
        message = with_details(str(item), item)
        server.window_log_message(
            types.LogMessageParams(_MESSAGE_TYPE[item.severity], f"{command}: {message}")
        )
        if item.severity == "error":
            counts["errors"] += 1
        elif item.severity == "warning":
            counts["warnings"] += 1
        filename = (item.source_span or item).filename
        if item.is_binary_only or filename not in texts:
            counts["unlocated"].append(
                {"severity": item.severity, "code": item.code, "message": message}
            )
            continue
        located.setdefault(uri_for(filename), []).append(
            lsp_diagnostic(
                item, texts, uri_for, encoding=server.encoding, source=f"aa2modulus {command}"
            )
        )
    server.record_findings(key, located)
    return counts
