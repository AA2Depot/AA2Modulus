"""The state one validation run shares across its checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ...core.diagnostics import DiagnosticSeverity, SourceFix
from ...language.catalog.model import LanguageCatalog
from ...metadata.snapshot import MetadataSnapshot
from ...model.records import Expression
from ...model.types import TypeId
from .declarations import DeclarationAnchor, declaration_help
from .labels import Labels
from .reporter import Reporter
from .scope import Scope


@dataclass(slots=True)
class ValidatorState:
    """Inputs and composed parts of one run: reporter, labels and variable scope.

    ``trigger_event_ids`` holds the current trigger's events while its body is
    checked. ``resolving_only`` marks the native pre-pass that reports only
    undefined variables.
    """

    metadata: MetadataSnapshot
    reporter: Reporter
    profile: Literal["strict", "native"]
    catalog: LanguageCatalog | None
    labels: Labels = field(init=False)
    scope: Scope = field(default_factory=Scope)
    trigger_event_ids: tuple[int, ...] | None = None
    resolving_only: bool = False
    declaration_anchor: DeclarationAnchor | None = None

    def __post_init__(self) -> None:
        self.labels = Labels(self.metadata, self.catalog)

    def undeclared_help(
        self, name: str, value_type: TypeId
    ) -> tuple[str | None, tuple[SourceFix, ...]]:
        """Help and fix that declare an undefined variable as a module global."""

        protected = self.catalog.protected_names if self.catalog is not None else frozenset()
        return declaration_help(name, value_type, self.declaration_anchor, protected)

    @property
    def native(self) -> bool:
        return self.profile == "native"

    @property
    def authoring_severity(self) -> DiagnosticSeverity:
        return "warning" if self.native else "error"

    def expression_type(self, expression: Expression) -> TypeId:
        """The type a check compares: native validation uses the declared return type."""

        if self.native:
            metadata = self.metadata.expression(expression.return_type, expression.id)
            if metadata is not None and metadata.declared_return_type is not None:
                return metadata.declared_return_type
        return expression.return_type
