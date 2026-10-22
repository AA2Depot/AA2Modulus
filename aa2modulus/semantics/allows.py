"""Source ``@allow(CODE)`` acknowledgement of known native hazards.

An attribute covers diagnostics located inside the item it prefixes, or whose
expansion origin (a macro call or trigger import) lies inside it. A covered
error is reported as a warning; nothing is hidden. Codes come from policy
``acknowledgeable``; everything else about an ``@allow`` is reported here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from ..core.diagnostics import Diagnostic, DiagnosticSeverity
from ..core.locations import SourceSpan
from ..syntax.ast import SourceAllow, SourceUnit

type AllowUse = tuple[int, int]
"""(index into the allows, index into that attribute's codes)."""


def _contains(target: SourceSpan, span: SourceSpan) -> bool:
    if span.filename != target.filename:
        return False
    start = (span.start_line, span.start_column)
    if start < (target.start_line, target.start_column):
        return False
    if target.end_line is None:
        return span.start_line == target.start_line
    return start <= (target.end_line, target.end_column or 1)


def _spans(diagnostic: Diagnostic) -> list[SourceSpan]:
    """The primary span, then each expansion origin, innermost first."""

    spans: list[SourceSpan] = []
    if diagnostic.source_span is not None:
        spans.append(diagnostic.source_span)
        spans.extend(note.span for note in diagnostic.source_span.related)
    spans.extend(note.span for note in diagnostic.related)
    return list(dict.fromkeys(replace(span, related=()) for span in spans))


def _covering(diagnostic: Diagnostic, allows: tuple[SourceAllow, ...]) -> AllowUse | None:
    """The innermost ``@allow`` naming the code, tried from the primary span outward."""

    for span in _spans(diagnostic):
        best: tuple[tuple[int, int], AllowUse] | None = None
        for index, allow in enumerate(allows):
            if diagnostic.code not in allow.codes or not _contains(allow.target_span, span):
                continue
            start = (allow.target_span.start_line, allow.target_span.start_column)
            if best is None or start > best[0]:
                best = (start, (index, allow.codes.index(diagnostic.code)))
        if best is not None:
            return best[1]
    return None


def _where(span: SourceSpan) -> str:
    return f"{span.filename}:{span.start_line}:{span.start_column}"


def acknowledge(
    diagnostics: Iterable[Diagnostic],
    allows: tuple[SourceAllow, ...],
    permitted: Iterable[str],
) -> tuple[tuple[Diagnostic, ...], frozenset[AllowUse]]:
    """Downgrade covered hazard errors and return which attribute codes were used.

    Idempotent: a covered hazard that is already a warning (acknowledged while
    validating a definition) only counts as a use.
    """

    permitted = frozenset(permitted)
    used: set[AllowUse] = set()
    result: list[Diagnostic] = []
    for diagnostic in diagnostics:
        use = (
            _covering(diagnostic, allows)
            if allows and diagnostic.code in permitted and diagnostic.severity != "info"
            else None
        )
        if use is None:
            result.append(diagnostic)
            continue
        used.add(use)
        if diagnostic.severity != "error":
            result.append(diagnostic)
            continue
        allow = allows[use[0]]
        result.append(
            replace(
                diagnostic,
                severity="warning",
                notes=(
                    *diagnostic.notes,
                    f"acknowledged by @allow({diagnostic.code}) at {_where(allow.source_span)}",
                ),
            )
        )
    return tuple(result), frozenset(used)


def _in_definition(allow: SourceAllow, unit: SourceUnit) -> bool:
    spans = (
        *(item.source_span for item in unit.macros),
        *(item.source_span for item in unit.templates),
    )
    return any(span is not None and _contains(span, allow.target_span) for span in spans)


def allow_diagnostics(
    unit: SourceUnit,
    permitted: Iterable[str],
    used: frozenset[AllowUse],
    *,
    report_unused: bool,
) -> tuple[Diagnostic, ...]:
    """Findings about the attributes themselves, in source order.

    ``UNUSED_ALLOW`` needs a completed validation and skips attributes inside
    macro and template definitions, whose findings depend on where they expand.
    """

    permitted = tuple(dict.fromkeys(permitted))
    diagnostics: list[Diagnostic] = []
    for index, allow in enumerate(unit.allows):
        definition = None
        for position, (code, span) in enumerate(zip(allow.codes, allow.code_spans, strict=True)):
            if code not in permitted:
                diagnostics.append(
                    _at(
                        span,
                        "error",
                        "ALLOW_NOT_PERMITTED",
                        f"{code} cannot be acknowledged with @allow",
                        help=(
                            "only known native hazards can be acknowledged ("
                            + ", ".join(permitted)
                            + "); fix this finding instead"
                            if permitted
                            else "the language policy permits no acknowledgements"
                        ),
                    )
                )
            elif (index, position) in used:
                diagnostics.append(
                    _at(
                        span,
                        "warning",
                        "NATIVE_HAZARD_ALLOWED",
                        f"@allow({code}) bypasses a known AAUnlimited hazard; "
                        "bypassing it is not recommended",
                        help="fix the underlying problem, then remove this @allow",
                    )
                )
            elif report_unused:
                if definition is None:
                    definition = _in_definition(allow, unit)
                if not definition:
                    diagnostics.append(
                        _at(
                            span,
                            "error",
                            "UNUSED_ALLOW",
                            f"@allow({code}) acknowledges nothing in the item it prefixes",
                            help="remove it, or move it before the item that reports the finding",
                        )
                    )
    return tuple(diagnostics)


def _at(
    span: SourceSpan, severity: DiagnosticSeverity, code: str, message: str, *, help: str
) -> Diagnostic:
    return Diagnostic(
        span.filename,
        span.start_line,
        span.start_column,
        severity,
        code,
        message,
        source_span=span,
        help=help,
    )
