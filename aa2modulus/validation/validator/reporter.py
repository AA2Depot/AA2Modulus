"""Collect located validation diagnostics."""

from __future__ import annotations

from ...core.diagnostics import Diagnostic, DiagnosticSeverity, SourceFix
from ...core.locations import BinaryLocation, SourceSpan


class Reporter:
    """Appends diagnostics located by source span, binary location or model path."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.diagnostics: list[Diagnostic] = []
        self.trigger_name: str | None = None

    def _location(
        self,
        node: object,
        path: tuple[str | int, ...],
        field_path: tuple[str | int, ...],
    ) -> tuple[str, int, int, tuple[str | int, ...], int | None]:
        source_span = getattr(node, "source_span", None)
        if isinstance(source_span, SourceSpan):
            filename = source_span.filename or self.filename
            return (
                filename,
                source_span.start_line,
                source_span.start_column,
                path + field_path,
                None,
            )
        binary_location = getattr(node, "binary_location", None)
        if isinstance(binary_location, BinaryLocation):
            return self.filename, 1, 1, binary_location.path + field_path, binary_location.offset
        return self.filename, 1, 1, path + field_path, None

    def add(
        self,
        node: object,
        path: tuple[str | int, ...],
        code: str,
        message: str,
        *,
        severity: DiagnosticSeverity = "error",
        field_path: tuple[str | int, ...] = (),
        notes: tuple[str, ...] = (),
        help: str | None = None,
        fixes: tuple[SourceFix, ...] = (),
    ) -> None:
        filename, line, column, diagnostic_path, offset = self._location(node, path, field_path)
        span = getattr(node, "source_span", None)
        self.diagnostics.append(
            Diagnostic(
                filename,
                line,
                column,
                severity,
                code,
                message,
                diagnostic_path,
                offset=offset,
                related=span.related if isinstance(span, SourceSpan) else (),
                source_span=span if isinstance(span, SourceSpan) else None,
                notes=(
                    *notes,
                    *((f'in trigger "{self.trigger_name}"',) if self.trigger_name else ()),
                ),
                help=help,
                fixes=fixes,
            )
        )
