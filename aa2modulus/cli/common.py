"""Helpers shared by the commands: exit codes, source reading, reports."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from ..context.limits import SourceLimits, resolve_source_limits
from ..core.diagnostics import Diagnostic, ExitCode, has_errors
from ..model.records import Module
from .render.diagnostics import count_text, write_diagnostics
from .render.snippets import SourceTexts
from .render.terminal import ReportSettings, render_options

EXIT_OK = int(ExitCode.OK)
EXIT_INPUT_ERROR = int(ExitCode.INPUT_ERROR)
EXIT_USAGE_ERROR = int(ExitCode.USAGE_ERROR)
EXIT_INTERNAL_ERROR = int(ExitCode.INTERNAL_ERROR)
DEFAULT_SETTINGS = ReportSettings()


def report(
    diagnostics: tuple[Diagnostic, ...],
    stream: TextIO,
    settings: ReportSettings,
    *,
    sources: dict[str, str] | None = None,
    module: Module | None = None,
    summary: str | None = None,
) -> None:
    """Print diagnostics and a closing summary to ``stream``."""

    write_diagnostics(
        diagnostics,
        stream,
        render_options(settings, stream),
        sources=SourceTexts(sources),
        module=module,
        summary=summary,
    )


def summary(prefix: str, diagnostics: tuple[Diagnostic, ...], success: str) -> str | None:
    """``<prefix>: 2 errors`` when errors exist, ``<success> with 1 warning`` otherwise."""

    counts = count_text(diagnostics)
    if not counts:
        return None
    return f"{prefix}: {counts}" if has_errors(diagnostics) else f"{success} with {counts}"


def read_source(
    path: Path, errors: TextIO, *, source_limits: SourceLimits | None = None
) -> tuple[str | None, int]:
    if not path.is_file():
        print(f"input source does not exist: {path}", file=errors)
        return None, EXIT_USAGE_ERROR
    try:
        limits = resolve_source_limits(source_limits)
        with path.open(encoding="utf-8", newline="") as source_file:
            # Keep one extra character so the compiler's common size diagnostic
            # rejects oversized input without reading the entire file.
            return source_file.read(
                min(limits.max_source_chars + 1, limits.max_total_source_chars + 1, sys.maxsize)
            ), EXIT_OK
    except UnicodeDecodeError as exc:
        print(f"source is not valid UTF-8: {path}: {exc}", file=errors)
        return None, EXIT_INPUT_ERROR
    except OSError as exc:
        print(f"could not read source {path}: {exc}", file=errors)
        return None, EXIT_INPUT_ERROR
