"""Source validation and compilation for unified `.aa2m` modules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from ..binary.writer import WriteError, WriterLimits, encode_module
from ..context.limits import SourceLimits
from ..context.operation import SourceContext
from ..context.resolver import SourceResolver
from ..core.diagnostics import Diagnostic, ValidationResult, binary_diagnostic
from ..core.locations import nearest_source_span, source_span_index
from ..metadata.loader import load_metadata
from ..metadata.snapshot import MetadataSnapshot
from ..model.records import Module
from ..pipeline.analysis import analyze_source
from ..validation.validator.module import validate_module


@dataclass(slots=True)
class CompileError(ValueError):
    """Raised when source or a model cannot be parsed, bound, validated, or written."""

    diagnostics: tuple[Diagnostic, ...]

    def __str__(self) -> str:
        return "\n".join(str(diagnostic) for diagnostic in self.diagnostics)


def _write_diagnostic(error: WriteError, *, filename: str, module: Module) -> Diagnostic:
    """Place a writer failure on the source node it came from, when there is one."""

    diagnostic = binary_diagnostic(filename, error, code="WRITE_ERROR")
    span = nearest_source_span(source_span_index(module, ()), diagnostic.path)
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


def parse_and_validate_source(
    source: str,
    *,
    filename: str | None = None,
    metadata: MetadataSnapshot | None = None,
    context: SourceContext | None = None,
    source_limits: SourceLimits | None = None,
    import_base: str | Path | None = None,
    source_resolver: SourceResolver | None = None,
    source_kind: Literal["module", "library"] = "module",
) -> tuple[Module | None, ValidationResult]:
    """Return SIR plus diagnostics, or no model for failures/library validation.

    Catalog configuration errors propagate as MetadataError. Writer constraints
    are checked only during compilation.
    """

    module, result, _ = _parse_and_validate_with_context(
        source,
        filename=filename,
        metadata=metadata,
        context=context,
        source_limits=source_limits,
        source_kind=source_kind,
        import_base=import_base,
        source_resolver=source_resolver,
    )
    return module, result


def _parse_and_validate_with_context(
    source: str,
    *,
    filename: str | None,
    metadata: MetadataSnapshot | None,
    context: SourceContext | None = None,
    source_limits: SourceLimits | None = None,
    import_base: str | Path | None = None,
    source_resolver: SourceResolver | None = None,
    source_kind: Literal["module", "library"] = "module",
) -> tuple[Module | None, ValidationResult, SourceContext]:
    context = SourceContext.resolve(
        context,
        filename=filename,
        metadata=metadata,
        source_limits=source_limits,
        import_base=import_base,
        source_resolver=source_resolver,
    )
    analysis = analyze_source(source, context=context, source_kind=source_kind)
    return (
        None if source_kind == "library" or analysis.failure is not None else analysis.module,
        analysis.result,
        context,
    )


def validate_source(
    source: str,
    *,
    filename: str | None = None,
    metadata: MetadataSnapshot | None = None,
    context: SourceContext | None = None,
    source_limits: SourceLimits | None = None,
    import_base: str | Path | None = None,
    source_resolver: SourceResolver | None = None,
    source_kind: Literal["module", "library"] = "module",
) -> ValidationResult:
    """Parse and validate unified source without producing binary output."""

    _, result = parse_and_validate_source(
        source,
        filename=filename,
        metadata=metadata,
        context=context,
        source_limits=source_limits,
        source_kind=source_kind,
        import_base=import_base,
        source_resolver=source_resolver,
    )
    return result


def compile_module(
    module: Module,
    *,
    filename: str = "<source>",
    metadata: MetadataSnapshot | None = None,
    profile: Literal["strict", "native"] = "strict",
    limits: WriterLimits | None = None,
) -> bytes:
    """Validate the selected model profile and emit its original GUI records.

    Raw provenance never relaxes semantic validation; use encode_module for
    structural recovery of representable data.
    Dependency lint is strict by default and warns in the native profile.
    Dependency strings/order are preserved.
    """

    metadata = metadata or load_metadata()
    result = validate_module(
        module,
        metadata=metadata,
        filename=filename,
        profile=profile,
    )
    if result.errors:
        raise CompileError(result.errors)
    try:
        return encode_module(
            metadata.resolve_module(module),
            limits=limits,
            reject_unresolved=profile == "strict",
        )
    except WriteError as exc:
        raise CompileError((_write_diagnostic(exc, filename=filename, module=module),)) from exc


def compile_source(
    source: str,
    *,
    filename: str | None = None,
    metadata: MetadataSnapshot | None = None,
    context: SourceContext | None = None,
    source_limits: SourceLimits | None = None,
    import_base: str | Path | None = None,
    source_resolver: SourceResolver | None = None,
    limits: WriterLimits | None = None,
) -> bytes:
    """Parse, validate, and compile unified `.aa2m` source to binary bytes."""

    data, _warnings = compile_source_with_warnings(
        source,
        filename=filename,
        metadata=metadata,
        context=context,
        source_limits=source_limits,
        import_base=import_base,
        source_resolver=source_resolver,
        limits=limits,
    )
    return data


def compile_source_with_warnings(
    source: str,
    *,
    filename: str | None = None,
    metadata: MetadataSnapshot | None = None,
    context: SourceContext | None = None,
    source_limits: SourceLimits | None = None,
    import_base: str | Path | None = None,
    source_resolver: SourceResolver | None = None,
    limits: WriterLimits | None = None,
) -> tuple[bytes, tuple[Diagnostic, ...]]:
    """``compile_source`` plus the non-error diagnostics of a successful compile."""

    module, result, _context = _parse_and_validate_with_context(
        source,
        filename=filename,
        metadata=metadata,
        context=context,
        source_limits=source_limits,
        import_base=import_base,
        source_resolver=source_resolver,
    )
    if module is None or result.errors:
        raise CompileError(result.errors or result.diagnostics)
    try:
        data = encode_module(
            module,
            limits=limits,
            reject_unresolved=True,
        )
    except WriteError as exc:
        raise CompileError(
            (_write_diagnostic(exc, filename=_context.filename, module=module),)
        ) from exc
    return data, result.diagnostics
