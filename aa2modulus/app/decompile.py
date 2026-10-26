"""Binary-to-unified-source decompilation for AAUnlimited modules."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from ..binary.reader import DecodeResult, TrailingBytes, decode_module
from ..context.operation import SourceContext
from ..core.diagnostics import Diagnostic
from ..core.locations import PathPart, SourceSpan, nearest_source_span, source_span_index
from ..decompile.format.module import format_module_with_diagnostics
from ..metadata.snapshot import MetadataSnapshot
from ..pipeline.analysis import analyze_source
from ..semantics.allows import acknowledge, allow_diagnostics
from ..syntax.ast import SourceUnit
from ..validation.validator.module import validate_module


@dataclass(frozen=True, slots=True)
class DecompileResult:
    """Recovered source, decoded input, and formatting/semantic diagnostics.

    Diagnostics are located in ``source`` under the recovered-source filename;
    each keeps its binary offset and structural path as evidence.
    """

    source: str
    decoded: DecodeResult
    diagnostics: tuple[Diagnostic, ...] = ()


def trailing_bytes_diagnostic(filename: str, trailing: TrailingBytes) -> Diagnostic:
    """The warning for bytes after the module data, which decompiled source cannot keep."""

    return Diagnostic(
        filename,
        1,
        1,
        "warning",
        "TRAILING_BYTES",
        f"{trailing.count} trailing bytes remain after the module data",
        offset=trailing.offset,
    )


def decompile_module(
    data: bytes | bytearray | memoryview,
    *,
    metadata: MetadataSnapshot | None = None,
    context: SourceContext | None = None,
    filename: str | None = None,
    source_filename: str = "<decompiled>",
    reject_trailing: bool = False,
) -> DecompileResult:
    """Decode binary data, recover source, and report fallback and semantic diagnostics.

    ``filename`` names the binary input; ``source_filename`` names the recovered
    text that diagnostics point into (for example the output path).
    """

    decoded = decode_module(data, reject_trailing=reject_trailing)
    operation = SourceContext.resolve(
        context,
        filename=(
            filename
            if filename is not None
            else context.filename
            if context is not None
            else "<binary>"
        ),
        metadata=metadata,
    )
    # A variable the module never declares may come from another module on the
    # card, but dependencies are not resolved. Recovery keeps it raw and warns;
    # the help names the declaration that makes the recovered source compile.
    semantic = tuple(
        replace(item, severity="warning") if item.code == "UNDEFINED_VARIABLE" else item
        for item in validate_module(
            decoded.module,
            metadata=operation.metadata,
            catalog=operation.catalog,
            filename=operation.filename,
        ).diagnostics
    )
    permitted = operation.source_policy.acknowledgeable_codes
    allows = _allow_anchors(semantic, permitted)
    source, fallback_diagnostics = format_module_with_diagnostics(
        decoded.module,
        context=operation,
        allows=allows,
    )
    diagnostics = _merge_fallbacks(fallback_diagnostics, semantic)
    located, unit = _locate_in_source(
        diagnostics, source, source_filename, operation, reparse=bool(allows)
    )
    if unit is not None and unit.allows:
        acknowledged, used = acknowledge(located, unit.allows, permitted)
        located = (
            *acknowledged,
            *allow_diagnostics(unit, permitted, used, report_unused=False),
        )
    return DecompileResult(source, decoded, located)


def _allow_anchors(
    diagnostics: Iterable[Diagnostic], permitted: Iterable[str]
) -> dict[tuple[PathPart, ...], tuple[str, ...]]:
    """Codes to acknowledge, keyed by the path of the smallest item recovered as source.

    The item is the innermost statement, else the event or local, else the
    trigger, else the module containing the finding's path.
    """

    permitted = frozenset(permitted)
    anchors: dict[tuple[PathPart, ...], list[str]] = {}
    for diagnostic in diagnostics:
        path = diagnostic.path
        if not diagnostic.is_error or diagnostic.code not in permitted or path[:1] != ("module",):
            continue
        anchor: tuple[PathPart, ...] = ("module",)
        if len(path) >= 3 and path[1] == "triggers" and isinstance(path[2], int):
            anchor = path[:3]
            if len(path) >= 5 and path[3] in {"events", "variables", "gui_actions"}:
                anchor = path[:5]
                if path[3] == "gui_actions":
                    while (
                        len(path) >= len(anchor) + 2
                        and path[len(anchor)] == "children"
                        and isinstance(path[len(anchor) + 1], int)
                    ):
                        anchor = path[: len(anchor) + 2]
        codes = anchors.setdefault(anchor, [])
        if diagnostic.code not in codes:
            codes.append(diagnostic.code)
    return {key: tuple(codes) for key, codes in anchors.items()}


def _merge_fallbacks(
    fallbacks: Iterable[Diagnostic], semantic: Iterable[Diagnostic]
) -> tuple[Diagnostic, ...]:
    """Report a node once: a semantic finding absorbs the raw fallback it caused."""

    fallbacks = tuple(fallbacks)
    absorbed: set[int] = set()
    merged: list[Diagnostic] = []
    for diagnostic in semantic:
        notes = list(diagnostic.notes)
        for position, fallback in enumerate(fallbacks):
            if _same_node(fallback.path, diagnostic.path):
                absorbed.add(position)
                notes.append("recovered as raw syntax, so it re-encodes byte-identically")
        merged.append(replace(diagnostic, notes=tuple(dict.fromkeys(notes))))
    kept = [item for position, item in enumerate(fallbacks) if position not in absorbed]
    return (*kept, *merged)


def _same_node(node: tuple[PathPart, ...], path: tuple[PathPart, ...]) -> bool:
    """Whether ``path`` names ``node`` or one of its scalar fields."""

    return (
        bool(node)
        and path[: len(node)] == node
        and not any(isinstance(part, int) for part in path[len(node) :])
    )


def _locate_in_source(
    diagnostics: tuple[Diagnostic, ...],
    source: str,
    source_filename: str,
    context: SourceContext,
    *,
    reparse: bool = False,
) -> tuple[tuple[Diagnostic, ...], SourceUnit | None]:
    """Point binary-located diagnostics at the recovered text.

    Recovery is lossless, so reparsing the text yields nodes at the same
    structural paths as the decoded module. A reparse failure is a recovery
    bug; the diagnostics then keep their binary locations. The reparsed unit
    is returned when the text was reparsed (always with ``reparse``).
    """

    if not reparse and not any(item.source_span is None and item.path for item in diagnostics):
        return diagnostics, None
    analysis = analyze_source(
        source, context=replace(context, filename=source_filename), validate=False
    )
    if analysis.module is None:
        return tuple(
            replace(item, notes=(*item.notes, "the recovered source could not be reparsed"))
            for item in diagnostics
        ), None
    index = source_span_index(analysis.module)
    return tuple(_relocated(item, index) for item in diagnostics), analysis.ast


def _relocated(diagnostic: Diagnostic, index: dict[tuple[PathPart, ...], SourceSpan]) -> Diagnostic:
    if diagnostic.source_span is not None or not diagnostic.path:
        return diagnostic
    span = nearest_source_span(index, diagnostic.path)
    if span is None:
        return diagnostic
    return replace(
        diagnostic,
        filename=span.filename,
        line=span.start_line,
        column=span.start_column,
        related=span.related,
        source_span=span,
    )
