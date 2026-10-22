"""The formatter's per-run state and the name and operator lookups built on it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ...core.diagnostics import Diagnostic
from ...core.locations import BinaryLocation, PathPart, RelatedLocation, SourceSpan
from ...core.source_names import is_source_name
from ...language.catalog.model import LanguageCatalog
from ...language.operators import OperatorDefinition
from ...language.policy import LanguagePolicy
from ...metadata.identities import NativeKind
from ...metadata.snapshot import MetadataSnapshot
from ...model.records import Expression
from ...model.types import TypeId
from .text import quote


@dataclass(slots=True)
class FormatContext:
    metadata: MetadataSnapshot
    policy: LanguagePolicy
    catalog: LanguageCatalog
    variables: dict[str, TypeId]
    filename: str
    diagnostics: list[Diagnostic]
    # Codes to acknowledge with `@allow`, keyed by the binary path of the
    # statement, event, local, trigger or module that contains each finding.
    allows: Mapping[tuple[PathPart, ...], tuple[str, ...]] = field(default_factory=dict)
    # Variables in scope declared `card` by inference (`CardInference`).
    cards: frozenset[str] = frozenset()

    def allow_lines(self, nodes: tuple[object, ...], indent: int) -> list[str]:
        """The ``@allow`` line for findings inside ``nodes``, rendered as one item."""

        codes: list[str] = []
        for node in nodes:
            location = getattr(node, "binary_location", None)
            if isinstance(location, BinaryLocation):
                codes.extend(self.allows.get(location.path, ()))
        if not codes:
            return []
        return [f"{' ' * indent}@allow({', '.join(dict.fromkeys(codes))})"]

    def raw_fallback(self, node: object, reason: str) -> None:
        span = getattr(node, "source_span", None)
        location = getattr(node, "binary_location", None)
        path = location.path if isinstance(location, BinaryLocation) else ()
        offset = location.offset if isinstance(location, BinaryLocation) else None
        filename = self.filename
        line = column = 1
        related: tuple[RelatedLocation, ...] = ()
        if isinstance(span, SourceSpan):
            filename = span.filename
            line = span.start_line
            column = span.start_column
            related = span.related
            offset = None
        self.diagnostics.append(
            Diagnostic(
                filename,
                line,
                column,
                "warning",
                "RAW_FALLBACK",
                f"recovered as raw syntax: {reason}",
                path,
                offset=offset,
                related=related,
                source_span=span if isinstance(span, SourceSpan) else None,
            )
        )


def _is_source_identifier(value: str) -> bool:
    return is_source_name(value, allow_qualified=False)


def is_bare_variable_name(value: str, context: FormatContext) -> bool:
    """Whether a variable can be written as a bare identifier (not keyword or protected)."""

    return _is_source_identifier(value) and value.casefold() not in context.catalog.protected_names


def declaration_name(value: str, context: FormatContext) -> str:
    return value if is_bare_variable_name(value, context) else quote(value)


def assignment_name(value: str, context: FormatContext) -> str:
    if is_bare_variable_name(value, context):
        return value
    return f"variable({quote(value)})"


def catalog_name(
    context: FormatContext, kind: NativeKind, identifier: int, scope: TypeId | None = None
) -> str | None:
    form = next(
        (
            item
            for item in context.catalog.forms(kind, identifier, scope)
            if item.canonical and item.reversible
        ),
        None,
    )
    return None if form is None else form.spelling


def operator_text(
    expression: Expression,
    context: FormatContext,
) -> tuple[OperatorDefinition, int] | None:
    parameter_types = tuple(item.return_type for item in expression.parameters)
    for operator in context.policy.operators:
        if (
            operator.expression_id == expression.id
            and operator.return_type == expression.return_type
            and operator.parameter_types == parameter_types
        ):
            return operator, operator.precedence
    return None
