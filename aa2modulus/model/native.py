"""Registry metadata records for native events, actions, expressions and named constants."""

from __future__ import annotations

from dataclasses import dataclass, field

from ._checks import coerce_type_id, optional_text, require_int, require_text
from .types import ModelError, TypeId
from .values import Value


@dataclass(frozen=True, slots=True)
class RegistryProvenance:
    """Source registration evidence; never a serialized module field."""

    source_file: str
    registration_sha256: str

    def __post_init__(self) -> None:
        require_text(self.source_file, "registry source file")
        require_text(self.registration_sha256, "registry registration fingerprint")


@dataclass(frozen=True, slots=True)
class EventMetadata:
    id: int
    name: str
    interactive_name: str = ""
    description: str = ""
    category: str | None = None
    parameter_types: tuple[TypeId, ...] = ()
    symbol: str | None = field(default=None, compare=False)
    provenance: RegistryProvenance | None = field(default=None, compare=False, kw_only=True)

    def __post_init__(self) -> None:
        require_int(self.id, "event metadata id")
        require_text(self.name, "event metadata name")
        require_text(self.interactive_name, "event interactive name")
        require_text(self.description, "event description")
        optional_text(self.category, "event category")
        optional_text(self.symbol, "event symbol")
        object.__setattr__(
            self,
            "parameter_types",
            tuple(coerce_type_id(value, "event parameter type") for value in self.parameter_types),
        )


@dataclass(frozen=True, slots=True)
class ActionMetadata:
    id: int
    name: str
    interactive_name: str = ""
    description: str = ""
    category: str | None = None
    parameter_types: tuple[TypeId, ...] = ()
    implementation: str | None = field(default=None, compare=False, kw_only=True)
    provenance: RegistryProvenance | None = field(default=None, compare=False, kw_only=True)

    def __post_init__(self) -> None:
        require_int(self.id, "action metadata id")
        require_text(self.name, "action metadata name")
        require_text(self.interactive_name, "action interactive name")
        require_text(self.description, "action description")
        optional_text(self.category, "action category")
        optional_text(self.implementation, "action implementation")
        object.__setattr__(
            self,
            "parameter_types",
            tuple(coerce_type_id(value, "action parameter type") for value in self.parameter_types),
        )


@dataclass(frozen=True, slots=True)
class ExpressionMetadata:
    id: int
    return_type: TypeId
    name: str
    interactive_name: str = ""
    description: str = ""
    category: str | None = None
    parameter_types: tuple[TypeId, ...] = ()
    declared_return_type: TypeId | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )
    implementation: str | None = field(default=None, compare=False, kw_only=True)
    provenance: RegistryProvenance | None = field(default=None, compare=False, kw_only=True)

    def __post_init__(self) -> None:
        require_int(self.id, "expression metadata id")
        object.__setattr__(self, "return_type", coerce_type_id(self.return_type))
        if self.declared_return_type is None:
            object.__setattr__(self, "declared_return_type", self.return_type)
        else:
            object.__setattr__(
                self,
                "declared_return_type",
                coerce_type_id(self.declared_return_type),
            )
        require_text(self.name, "expression metadata name")
        require_text(self.interactive_name, "expression interactive name")
        require_text(self.description, "expression description")
        optional_text(self.category, "expression category")
        optional_text(self.implementation, "expression implementation")
        object.__setattr__(
            self,
            "parameter_types",
            tuple(
                coerce_type_id(value, "expression parameter type") for value in self.parameter_types
            ),
        )


@dataclass(frozen=True, slots=True)
class NamedConstantMetadata:
    id: int
    value_type: TypeId
    name: str
    interactive_name: str = ""
    description: str = ""
    category: str | None = None
    value: Value | None = None
    value_expression: str | None = None
    resolved_value: Value | None = field(default=None, compare=False, kw_only=True)
    provenance: RegistryProvenance | None = field(default=None, compare=False, kw_only=True)

    def __post_init__(self) -> None:
        require_int(self.id, "named constant metadata id")
        object.__setattr__(self, "value_type", coerce_type_id(self.value_type))
        require_text(self.name, "named constant name")
        require_text(self.interactive_name, "named constant interactive name")
        require_text(self.description, "named constant description")
        optional_text(self.category, "named constant category")
        optional_text(self.value_expression, "named constant value expression")
        if self.resolved_value is not None and self.resolved_value.type != self.value_type:
            raise ModelError("resolved named constant value type does not match scope")
