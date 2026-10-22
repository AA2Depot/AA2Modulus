"""Shared diagnostics and command exit-code contracts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal

from .locations import RelatedLocation, SourceSpan

DiagnosticSeverity = Literal["error", "warning", "info"]

NATIVE_HAZARD_CODES = frozenset(
    {
        "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH",
        "NATIVE_DEFECTIVE_EXPRESSION",
        "REVIEWED_VALUE_TYPE_MISMATCH",
    }
)
"""Validator codes that report a known AAUnlimited hazard rather than an authoring
mistake. Policy ``acknowledgeable`` may list only these."""


@dataclass(frozen=True, slots=True)
class SourceFix:
    """One concrete edit that resolves a diagnostic: replace ``span`` with ``replacement``.

    ``title`` names the edit for an editor's quick-fix menu. The span's end
    column is inclusive, as in every source span.
    """

    title: str
    span: SourceSpan
    replacement: str

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("source fix title cannot be empty")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A source or binary diagnostic with a stable printable form.

    ``line``/``column``/``source_span`` locate the finding in source. ``path``
    and ``offset`` are structural and binary evidence; they never appear in the
    printed headline. ``notes`` are unlocated context lines and ``help`` says
    how to fix the finding when that is known; ``fixes`` are the concrete edits
    behind that help, for editors (the printed forms never show them).
    """

    filename: str
    line: int
    column: int
    severity: DiagnosticSeverity
    code: str
    message: str
    path: tuple[str | int, ...] = field(default=(), compare=False)
    offset: int | None = field(default=None, compare=False, kw_only=True)
    related: tuple[RelatedLocation, ...] = field(default=(), compare=False, kw_only=True)
    source_span: SourceSpan | None = field(default=None, compare=False, kw_only=True)
    notes: tuple[str, ...] = field(default=(), compare=False, kw_only=True)
    help: str | None = field(default=None, compare=False, kw_only=True)
    fixes: tuple[SourceFix, ...] = field(default=(), compare=False, kw_only=True)

    def __post_init__(self) -> None:
        if not self.filename:
            raise ValueError("diagnostic filename cannot be empty")
        if self.line < 1 or self.column < 1:
            raise ValueError("diagnostic locations are one-based")
        if self.severity not in {"error", "warning", "info"}:
            raise ValueError("unsupported diagnostic severity")
        if not self.code:
            raise ValueError("diagnostic code cannot be empty")
        if not self.message:
            raise ValueError("diagnostic message cannot be empty")
        object.__setattr__(self, "path", tuple(self.path))
        object.__setattr__(self, "related", tuple(self.related))
        if self.offset is not None and self.offset < 0:
            raise ValueError("diagnostic offset must be a nonnegative integer")
        object.__setattr__(self, "notes", tuple(self.notes))
        if not all(self.notes):
            raise ValueError("diagnostic notes must be nonempty strings")
        if self.help is not None and not self.help:
            raise ValueError("diagnostic help must be a nonempty string")
        object.__setattr__(self, "fixes", tuple(self.fixes))

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    @property
    def is_binary_only(self) -> bool:
        """Whether the only known location is a binary offset."""

        return self.source_span is None and self.offset is not None

    @property
    def location(self) -> str:
        """``file:line:col``, or ``file@0xOFFSET`` for a binary-only finding."""

        if self.is_binary_only:
            assert self.offset is not None
            return f"{self.filename}@0x{self.offset:X}"
        return f"{self.filename}:{self.line}:{self.column}"

    def __str__(self) -> str:
        """The ``short`` form: one headline plus one line per related location."""

        result = f"{self.location}: {self.severity}[{self.code}]: {self.message}"
        for note in self.related:
            span = note.span
            result += (
                f"\n{span.filename}:{span.start_line}:{span.start_column}: note: {note.message}"
            )
        return result


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """All diagnostics produced for one validation or parsing operation."""

    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.is_error)

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == "warning")

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:
        return self.is_valid


class ExitCode(IntEnum):
    """Stable CLI exit codes documented by the project contract."""

    OK = 0
    INPUT_ERROR = 1
    USAGE_ERROR = 2
    INTERNAL_ERROR = 3


def has_errors(diagnostics: Iterable[Diagnostic]) -> bool:
    """Return whether a diagnostic sequence contains an error."""

    return any(diagnostic.is_error for diagnostic in diagnostics)


def format_path(path: tuple[str | int, ...]) -> str:
    """Render a structural path consistently across diagnostics."""

    if not path:
        return "<root>"
    result = ""
    for part in path:
        if isinstance(part, int):
            result += f"[{part}]"
        elif result:
            result += f".{part}"
        else:
            result = part
    return result


def binary_diagnostic(
    filename: str,
    error: object,
    *,
    code: str = "BINARY_ERROR",
) -> Diagnostic:
    """Adapt decoder/writer-like failures into a structured diagnostic."""

    message = getattr(error, "message", None) or str(error)
    offset = getattr(error, "offset", None)
    path = tuple(getattr(error, "path", ()))
    return Diagnostic(filename, 1, 1, "error", code, message, path, offset=offset)


def exit_code_for_diagnostics(
    diagnostics: Iterable[Diagnostic],
    *,
    strict: bool = True,
) -> ExitCode:
    """Map diagnostics to the input-error portion of the CLI contract."""

    if strict and has_errors(diagnostics):
        return ExitCode.INPUT_ERROR
    return ExitCode.OK


def exit_code_for_inspection(
    diagnostics: Iterable[Diagnostic],
    *,
    strict: bool,
    has_trailing_bytes: bool = False,
) -> ExitCode:
    """Map inspection warnings/errors while preserving permissive inspection."""

    if strict and (has_trailing_bytes or has_errors(diagnostics)):
        return ExitCode.INPUT_ERROR
    return ExitCode.OK
