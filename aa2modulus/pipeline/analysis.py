"""Shared compiler analysis retaining completed stages for editor consumers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from ..context.limits import SourceLimitError
from ..context.operation import SourceContext
from ..core.diagnostics import Diagnostic, ValidationResult
from ..core.locations import RelatedLocation
from ..hir.nodes import BoundModule
from ..lowering.module import lower_bound_module
from ..model.records import Module
from ..semantics.allows import acknowledge, allow_diagnostics
from ..semantics.binding.module import bind_source_ast
from ..semantics.binding.state import SourceBindingError
from ..syntax.ast import SourceModule, SourceUnit
from ..syntax.braces import brace_hints
from ..syntax.imports import (
    SourceDependency,
    SourceImportError,
    check_source_graph_text,
    resolve_source_imports,
)
from ..syntax.parser.errors import SourceParseError
from ..syntax.parser.units import parse_source_unit
from ..syntax.recovery import syntax_diagnostics
from ..validation.validator.module import validate_module

type SourceFailure = SourceParseError | SourceBindingError | SourceImportError | SourceLimitError


@dataclass(frozen=True, slots=True)
class SourceAnalysis:
    """One operation's source stages; never reused across text versions.

    ``ast`` is the authored root, ``composed_ast`` includes imported definitions,
    and ``module`` is lowered SIR. Library analysis uses an internal empty module
    for definition validation; application APIs do not expose it as output.
    """

    context: SourceContext
    ast: SourceUnit | None = None
    composed_ast: SourceUnit | None = None
    bound: BoundModule | None = None
    module: Module | None = None
    result: ValidationResult = field(default_factory=ValidationResult)
    dependencies: tuple[SourceDependency, ...] = ()
    failure: SourceFailure | None = field(default=None, compare=False, repr=False)
    source: str = field(default="", compare=False, repr=False, kw_only=True)


def _merge_diagnostics(
    validation: ValidationResult, definitions: tuple[Diagnostic, ...]
) -> ValidationResult:
    """Merge emitted and definition diagnostics without dropping expansion notes."""

    definition_notes: dict[Diagnostic, tuple[RelatedLocation, ...]] = {}
    for item in definitions:
        definition_notes[item] = tuple(
            dict.fromkeys((*definition_notes.get(item, ()), *item.related))
        )
    emitted = set(validation.diagnostics)
    return ValidationResult(
        (
            *(
                replace(
                    item,
                    related=tuple(dict.fromkeys((*item.related, *definition_notes.get(item, ())))),
                )
                for item in validation.diagnostics
            ),
            *(item for item in definitions if item not in emitted),
        )
    )


def analyze_source(
    source: str,
    *,
    context: SourceContext,
    source_kind: Literal["module", "library"] = "module",
    validate: bool = True,
) -> SourceAnalysis:
    """Run the compiler pipeline, retaining stages before an input failure.

    ``validate=False`` skips final semantic validation (decompiled-source location).
    Configuration errors and unexpected provider/programming errors propagate.
    """

    ast = None
    composed = None
    bound = None
    module = None
    dependencies: list[SourceDependency] = []
    failure: SourceFailure | None = None
    try:
        check_source_graph_text(source, context)
        ast = parse_source_unit(
            source,
            filename=context.filename,
            source_limits=context.source_limits,
            kind=source_kind,
        )
        composed = resolve_source_imports(
            ast, context, root_chars=len(source), dependencies=dependencies
        )
        binding_input = composed
        if source_kind == "library":
            binding_input = replace(composed, module=SourceModule("<library>"))
        bound = bind_source_ast(binding_input, context=context)
        module = lower_bound_module(bound, context=context)
        result = ValidationResult(bound.diagnostics)
        if validate:
            validation = validate_module(
                module,
                metadata=context.metadata,
                filename=context.filename,
                catalog=context.catalog,
            )
            permitted = context.source_policy.acknowledgeable_codes
            # Acknowledge before merging, so an expanded hazard equals its
            # definition-time copy (already a warning) and is reported once.
            emitted, _used = acknowledge(validation.diagnostics, composed.allows, permitted)
            merged = _merge_diagnostics(ValidationResult(emitted), bound.diagnostics)
            diagnostics, used = acknowledge(merged.diagnostics, composed.allows, permitted)
            result = ValidationResult(
                (
                    *diagnostics,
                    *allow_diagnostics(composed, permitted, used, report_unused=True),
                )
            )
    except SourceParseError as exc:
        failure = exc
        result = ValidationResult(
            brace_hints(source, syntax_diagnostics(source, exc, context), context)
        )
    except SourceBindingError as exc:
        failure = exc
        result = ValidationResult(
            (
                *exc.diagnostics,
                *(
                    ()
                    if composed is None
                    else allow_diagnostics(
                        composed,
                        context.source_policy.acknowledgeable_codes,
                        frozenset(),
                        report_unused=False,
                    )
                ),
            )
        )
    except (SourceImportError, SourceLimitError) as exc:
        failure = exc
        result = ValidationResult((exc.diagnostic,))
    return SourceAnalysis(
        context, ast, composed, bound, module, result, tuple(dependencies), failure, source=source
    )
