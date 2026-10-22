"""Binding errors, the error collector and the per-operation binding context."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...core.diagnostics import Diagnostic, SourceFix
from ...hir.limits import BindingBudget
from ...hir.symbols import BoundReference, ResolvedConstant, SourceDeclaration
from ...language.catalog.model import LanguageCatalog
from ...language.policy import LanguagePolicy
from ...language.types import (
    CARD,
    SourceType,
)
from ...metadata.snapshot import MetadataSnapshot
from ...model.types import ValueType
from ...syntax.ast import (
    SourceAllow,
    SourceMacro,
    SourceTriggerTemplate,
)
from ...validation.validator.declarations import DeclarationAnchor, declaration_help
from ..expansion import (
    ExpansionBudget,
    MacroTemplate,
)


class SourceBindingError(ValueError):
    """Raised when source names or types cannot be bound.

    ``diagnostic`` is the first error; ``diagnostics`` holds every independent
    error of the operation in source order, starting with it.
    """

    def __init__(self, diagnostic: Diagnostic, diagnostics: tuple[Diagnostic, ...] = ()) -> None:
        self.diagnostic = diagnostic
        self.diagnostics = diagnostics or (diagnostic,)
        super().__init__(diagnostic.message)


class Poisoned(Exception):
    """A use of a definition whose own error is already collected; reports nothing."""


class ErrorLimit(Exception):
    """More binding errors than ``SourceLimits.max_binding_errors``."""


# Declaration-level conflicts that leave no sound scope to continue binding in.
_STOP_CODES = frozenset({"DUPLICATE_CONST", "CONST_CYCLE", "TEMPLATE_TRIGGER_NAME_COLLISION"})


@dataclass(slots=True)
class ErrorCollector:
    """Independent errors of one strict binding, shared by every derived context.

    ``failures`` counts collected errors and silently skipped uses of poisoned
    definitions, so a definition can tell whether its own body bound cleanly.
    """

    limit: int
    errors: list[Diagnostic] = field(default_factory=list)
    suppressed: int = 0
    poisoned_macros: set[str] = field(default_factory=set)
    poisoned_templates: set[str] = field(default_factory=set)

    @property
    def failures(self) -> int:
        return len(self.errors) + self.suppressed

    def mark(self) -> int:
        """The failure count to hand to ``failed_since`` after binding a body."""

        return self.failures

    def failed_since(self, mark: int) -> bool:
        return self.failures > mark

    def record(self, exc: SourceBindingError) -> None:
        if exc.diagnostic.code in _STOP_CODES:
            raise exc
        self.errors.extend(exc.diagnostics)
        if len(self.errors) > self.limit:
            raise ErrorLimit


@dataclass(slots=True)
class BindContext:
    metadata: MetadataSnapshot
    source_policy: LanguagePolicy
    filename: str
    globals: dict[str, SourceType]
    locals: dict[str, SourceType]
    catalog: LanguageCatalog = field(kw_only=True)
    binding_budget: BindingBudget = field(kw_only=True)
    global_declarations: dict[str, SourceDeclaration] = field(default_factory=dict)
    local_declarations: dict[str, SourceDeclaration] = field(default_factory=dict)
    macros: dict[str, MacroTemplate] = field(default_factory=dict)
    macro_definition: SourceMacro | None = None
    template_definition: SourceTriggerTemplate | None = None
    expansion_budget: ExpansionBudget | None = None
    depth: int = 2
    nesting: int = 0
    loop_depth: int = 0
    input_diagnostics: list[Diagnostic] = field(default_factory=list)
    references: list[BoundReference] = field(default_factory=list)
    constants: dict[str, ResolvedConstant] = field(default_factory=dict)
    # Module-item constants, invisible in macro and template contexts (hint only).
    hidden_constants: dict[str, ResolvedConstant] = field(default_factory=dict)
    # Strict binding collects errors at statement and item boundaries; editor
    # views leave this unset, so every error raises to their own recovery.
    collector: ErrorCollector | None = None
    # `@allow` attributes, applied when a macro or template definition is validated.
    allows: tuple[SourceAllow, ...] = ()
    # Where a suggested declaration for an undefined variable goes.
    declaration_anchor: DeclarationAnchor | None = None

    def variable_type(self, name: str) -> SourceType | None:
        global_type = self.globals.get(name)
        if global_type is not None:
            return global_type
        return self.locals.get(name)

    def undeclared_help(
        self, name: str, value_type: SourceType | None
    ) -> tuple[str | None, tuple[SourceFix, ...]]:
        """Help and fix that declare an undefined variable as a module global."""

        if value_type is None:
            return None, ()
        wire = ValueType.INT if value_type is CARD else value_type
        return declaration_help(name, wire, self.declaration_anchor, self.catalog.protected_names)

    def variable_declaration(self, name: str) -> SourceDeclaration | None:
        if name in self.globals:
            return self.global_declarations.get(name)
        if name in self.locals:
            return self.local_declarations.get(name)
        return None

    def fork_references(self) -> BindContext:
        """Isolate speculative references while preserving the current scope."""

        return replace(self, references=[])

    def derive(
        self,
        *,
        locals_: dict[str, SourceType],
        local_declarations: dict[str, SourceDeclaration],
        constants: dict[str, ResolvedConstant],
        hidden_constants: dict[str, ResolvedConstant],
        macro_definition: SourceMacro | None = None,
        template_definition: SourceTriggerTemplate | None = None,
        depth: int = 2,
    ) -> BindContext:
        """A fresh scope for one definition body.

        It shares the module-wide state (macros, budgets, input diagnostics and
        the collector) but starts with no globals, references or allows.
        """

        return replace(
            self,
            globals={},
            locals=locals_,
            global_declarations={},
            local_declarations=local_declarations,
            macro_definition=macro_definition,
            template_definition=template_definition,
            depth=depth,
            nesting=0,
            loop_depth=0,
            references=[],
            constants=constants,
            hidden_constants=hidden_constants,
            allows=(),
        )

    def is_slot(self, name: str) -> bool:
        return self.template_definition is not None and any(
            item.name == name for item in self.template_definition.slots
        )
