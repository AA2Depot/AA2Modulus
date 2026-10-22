"""SIR records: expressions, events, actions, variables, GUI trees, triggers and modules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ._checks import (
    as_tuple,
    coerce_type_id,
    require_field,
    require_int,
    require_mapping,
    require_text,
)
from .native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from .node import SerializedNode
from .types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, ModelError, TypeId
from .values import Value


@dataclass(frozen=True, slots=True)
class NamedConstantRef(SerializedNode):
    """A type-scoped named-constant ID plus optional resolved metadata."""

    value_type: TypeId
    id: int
    metadata: NamedConstantMetadata | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "value_type", coerce_type_id(self.value_type))
        require_int(self.id, "named constant id")
        if self.metadata is not None:
            if self.metadata.id != self.id:
                raise ModelError("named constant metadata id does not match raw id")
            if self.metadata.value_type != self.value_type:
                raise ModelError("named constant metadata type does not match scope")

    def to_ir(self) -> dict[str, Any]:
        return {"type": int(self.value_type), "id": self.id}

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> NamedConstantRef:
        data = require_mapping(data, "named constant IR")
        return cls(require_field(data, "type"), require_field(data, "id"))


@dataclass(frozen=True, slots=True)
class Expression(SerializedNode):
    """A recursive expression preserving its raw, type-scoped ID."""

    return_type: TypeId
    id: int
    constant: Value | None = None
    variable_name: str | None = None
    named_constant: NamedConstantRef | None = None
    parameters: tuple[Expression, ...] = ()
    metadata: ExpressionMetadata | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "return_type", coerce_type_id(self.return_type))
        require_int(self.id, "expression id")
        object.__setattr__(self, "parameters", as_tuple(self.parameters, "expression parameters"))

        payload_fields = (
            self.constant is not None,
            self.variable_name is not None,
            self.named_constant is not None,
        )
        if self.id == EXPR_CONSTANT:
            if (
                self.constant is None
                or self.variable_name is not None
                or self.named_constant is not None
                or self.parameters
            ):
                raise ModelError("constant expressions require only a Value payload")
        elif self.id == EXPR_VAR:
            if (
                self.variable_name is None
                or self.constant is not None
                or self.named_constant is not None
                or self.parameters
            ):
                raise ModelError("variable expressions require only a variable name")
            require_text(self.variable_name, "variable name")
        elif self.id == EXPR_NAMEDCONSTANT:
            if (
                self.named_constant is None
                or self.constant is not None
                or self.variable_name is not None
                or self.parameters
            ):
                raise ModelError("named-constant expressions require only a named constant")
        elif any(payload_fields):
            raise ModelError("function expressions cannot carry a special expression payload")

        if self.metadata is not None:
            if self.metadata.id != self.id:
                raise ModelError("expression metadata id does not match raw id")
            if self.metadata.return_type != self.return_type:
                raise ModelError("expression metadata type does not match scope")

    @property
    def expression_id(self) -> int:
        return self.id

    @property
    def actual_parameters(self) -> tuple[Expression, ...]:
        return self.parameters

    @property
    def named_constant_id(self) -> int | None:
        if self.named_constant is None:
            return None
        return self.named_constant.id

    def to_ir(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "return_type": int(self.return_type),
            "id": self.id,
        }
        if self.id == EXPR_CONSTANT:
            assert self.constant is not None
            result["constant"] = self.constant.to_ir()
        elif self.id == EXPR_VAR:
            result["variable_name"] = self.variable_name
        elif self.id == EXPR_NAMEDCONSTANT:
            result["named_constant_id"] = self.named_constant_id
        else:
            result["parameters"] = [parameter.to_ir() for parameter in self.parameters]
        return result

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> Expression:
        data = require_mapping(data, "expression IR")
        return_type = require_field(data, "return_type")
        expression_id = require_field(data, "id")
        if expression_id == EXPR_CONSTANT:
            return cls(
                return_type, expression_id, constant=Value.from_ir(require_field(data, "constant"))
            )
        if expression_id == EXPR_VAR:
            return cls(
                return_type, expression_id, variable_name=require_field(data, "variable_name")
            )
        if expression_id == EXPR_NAMEDCONSTANT:
            named_id = require_field(data, "named_constant_id")
            return cls(
                return_type,
                expression_id,
                named_constant=NamedConstantRef(return_type, named_id),
            )
        return cls(
            return_type,
            expression_id,
            parameters=tuple(Expression.from_ir(value) for value in data.get("parameters", ())),
        )


@dataclass(frozen=True, slots=True)
class Event(SerializedNode):
    """A parameterised event reference retaining unknown numeric IDs."""

    id: int
    parameters: tuple[Expression, ...] = ()
    metadata: EventMetadata | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )

    def __post_init__(self) -> None:
        require_int(self.id, "event id")
        object.__setattr__(self, "parameters", as_tuple(self.parameters, "event parameters"))
        if self.metadata is not None and self.metadata.id != self.id:
            raise ModelError("event metadata id does not match raw id")

    @property
    def event_id(self) -> int:
        return self.id

    @property
    def actual_parameters(self) -> tuple[Expression, ...]:
        return self.parameters

    def to_ir(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parameters": [parameter.to_ir() for parameter in self.parameters],
        }

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> Event:
        data = require_mapping(data, "event IR")
        return cls(
            require_field(data, "id"),
            tuple(Expression.from_ir(value) for value in data.get("parameters", ())),
        )


@dataclass(frozen=True, slots=True)
class ActionCall(SerializedNode):
    """A parameterised action reference retaining unknown numeric IDs."""

    id: int
    parameters: tuple[Expression, ...] = ()
    metadata: ActionMetadata | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )

    def __post_init__(self) -> None:
        require_int(self.id, "action id")
        object.__setattr__(self, "parameters", as_tuple(self.parameters, "action parameters"))
        if self.metadata is not None and self.metadata.id != self.id:
            raise ModelError("action metadata id does not match raw id")

    @property
    def action_id(self) -> int:
        return self.id

    @property
    def actual_parameters(self) -> tuple[Expression, ...]:
        return self.parameters

    def to_ir(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parameters": [parameter.to_ir() for parameter in self.parameters],
        }

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> ActionCall:
        data = require_mapping(data, "action IR")
        return cls(
            require_field(data, "id"),
            tuple(Expression.from_ir(value) for value in data.get("parameters", ())),
        )


@dataclass(frozen=True, slots=True)
class Variable(SerializedNode):
    """A local trigger variable and its default expression."""

    type: TypeId
    name: str
    default_expression: Expression

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", coerce_type_id(self.type))
        require_text(self.name, "variable name")

    @property
    def default_value(self) -> Expression:
        return self.default_expression

    def to_ir(self) -> dict[str, Any]:
        return {
            "type": int(self.type),
            "name": self.name,
            "default_expression": self.default_expression.to_ir(),
        }

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> Variable:
        data = require_mapping(data, "variable IR")
        return cls(
            require_field(data, "type"),
            require_field(data, "name"),
            Expression.from_ir(require_field(data, "default_expression")),
        )


@dataclass(frozen=True, slots=True)
class GlobalVariable(SerializedNode):
    """A serialized module global without its runtime-only ID."""

    type: TypeId
    name: str
    default_value: Value
    current_value: Value
    initialized: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", coerce_type_id(self.type))
        require_text(self.name, "global variable name")
        if not isinstance(self.initialized, bool):
            raise TypeError("initialized must be a boolean")

    def to_ir(self) -> dict[str, Any]:
        return {
            "type": int(self.type),
            "name": self.name,
            "default_value": self.default_value.to_ir(),
            "current_value": self.current_value.to_ir(),
            "initialized": self.initialized,
        }

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> GlobalVariable:
        data = require_mapping(data, "global variable IR")
        return cls(
            require_field(data, "type"),
            require_field(data, "name"),
            Value.from_ir(require_field(data, "default_value")),
            Value.from_ir(require_field(data, "current_value")),
            require_field(data, "initialized"),
        )


@dataclass(frozen=True, slots=True)
class GuiAction(SerializedNode):
    """A nested GUI action tree node; no runtime parent is stored."""

    action: ActionCall
    children: tuple[GuiAction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "children", as_tuple(self.children, "GUI action children"))

    def to_ir(self) -> dict[str, Any]:
        return {
            "action": self.action.to_ir(),
            "children": [child.to_ir() for child in self.children],
        }

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> GuiAction:
        data = require_mapping(data, "GUI action IR")
        return cls(
            ActionCall.from_ir(require_field(data, "action")),
            tuple(GuiAction.from_ir(value) for value in data.get("children", ())),
        )


@dataclass(frozen=True, slots=True)
class Trigger(SerializedNode):
    """A serialized trigger containing its GUI tree, not flattened runtime actions."""

    name: str
    events: tuple[Event, ...] = ()
    variables: tuple[Variable, ...] = ()
    gui_actions: tuple[GuiAction, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.name, "trigger name")
        object.__setattr__(self, "events", as_tuple(self.events, "trigger events"))
        object.__setattr__(self, "variables", as_tuple(self.variables, "trigger variables"))
        object.__setattr__(self, "gui_actions", as_tuple(self.gui_actions, "trigger GUI actions"))

    def to_ir(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "events": [event.to_ir() for event in self.events],
            "variables": [variable.to_ir() for variable in self.variables],
            "gui_actions": [action.to_ir() for action in self.gui_actions],
        }

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> Trigger:
        data = require_mapping(data, "trigger IR")
        return cls(
            require_field(data, "name"),
            tuple(Event.from_ir(value) for value in data.get("events", ())),
            tuple(Variable.from_ir(value) for value in data.get("variables", ())),
            tuple(GuiAction.from_ir(value) for value in data.get("gui_actions", ())),
        )


@dataclass(frozen=True, slots=True)
class Module(SerializedNode):
    """The serialized module root."""

    name: str
    description: str = ""
    triggers: tuple[Trigger, ...] = ()
    globals: tuple[GlobalVariable, ...] = ()
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.name, "module name")
        require_text(self.description, "module description")
        object.__setattr__(self, "triggers", as_tuple(self.triggers, "module triggers"))
        object.__setattr__(self, "globals", as_tuple(self.globals, "module globals"))
        object.__setattr__(self, "dependencies", as_tuple(self.dependencies, "module dependencies"))
        if any(not isinstance(value, str) for value in self.dependencies):
            raise TypeError("module dependencies must be strings")

    def to_ir(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": [trigger.to_ir() for trigger in self.triggers],
            "globals": [variable.to_ir() for variable in self.globals],
            "dependencies": list(self.dependencies),
        }

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> Module:
        data = require_mapping(data, "module IR")
        return cls(
            require_field(data, "name"),
            data.get("description", ""),
            tuple(Trigger.from_ir(value) for value in data.get("triggers", ())),
            tuple(GlobalVariable.from_ir(value) for value in data.get("globals", ())),
            tuple(data.get("dependencies", ())),
        )
