"""Bounded encoder for the AAUnlimited module binary format."""

from __future__ import annotations

import struct
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import NoReturn

from ..core.diagnostics import format_path
from ..model.records import (
    ActionCall,
    Event,
    Expression,
    GlobalVariable,
    GuiAction,
    Module,
    NamedConstantRef,
    Trigger,
    Variable,
)
from ..model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, ValueType
from ..model.values import Value
from .codec import NodeBudget, check_limit_fields


@dataclass(frozen=True, slots=True)
class WriterLimits:
    """Limits applied before the writer emits data or recurses."""

    max_string_code_units: int = 1_048_576
    max_vector_elements: int = 1_000_000
    max_recursion_depth: int = 256
    max_encoded_nodes: int = 1_000_000
    max_output_bytes: int = 67_108_864

    def __post_init__(self) -> None:
        check_limit_fields(self)


_PACK_RANGE_TEXT = {
    "<i": "is outside the int32 range (-2147483648 to 2147483647)",
    "<I": "is outside the uint32 range (0 to 4294967295)",
    "<f": "is outside the float32 range",
}


class WriteError(ValueError):
    """An invalid model, unsupported value, or violated writer limit."""

    def __init__(
        self,
        message: str,
        *,
        offset: int,
        path: tuple[str | int, ...] = (),
    ) -> None:
        self.message = message
        self.offset = offset
        self.path = tuple(path)
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.message} at output offset 0x{self.offset:X} (path {format_path(self.path)})"


class BinaryWriter:
    """Write one bounded AAUnlimited module from the logical model."""

    def __init__(
        self,
        limits: WriterLimits | None = None,
        *,
        reject_unresolved: bool = False,
    ) -> None:
        self.limits = limits if limits is not None else WriterLimits()
        if not isinstance(self.limits, WriterLimits):
            raise TypeError("limits must be a WriterLimits instance")
        if not isinstance(reject_unresolved, bool):
            raise TypeError("reject_unresolved must be a boolean")
        self.reject_unresolved = reject_unresolved
        self._reset()

    def _reset(self) -> None:
        self._buffer = bytearray()
        self._path: list[str | int] = []
        self._recursion_depth = 0
        self._nodes = NodeBudget(self.limits.max_encoded_nodes, "encoded", "writing")

    @property
    def position(self) -> int:
        return len(self._buffer)

    @property
    def path(self) -> tuple[str | int, ...]:
        return tuple(self._path)

    @contextmanager
    def at_path(self, part: str | int) -> Iterator[None]:
        self._path.append(part)
        try:
            yield
        finally:
            self._path.pop()

    def _error(
        self,
        message: str,
        *,
        offset: int | None = None,
        path: tuple[str | int, ...] | None = None,
    ) -> NoReturn:
        raise WriteError(
            message,
            offset=self.position if offset is None else offset,
            path=self.path if path is None else path,
        )

    def _require_instance[T](self, value: object, expected: type[T], label: str) -> T:
        if not isinstance(value, expected):
            self._error(f"{label} must be a {expected.__name__}")
        return value

    def _append(self, data: bytes) -> None:
        if len(self._buffer) > self.limits.max_output_bytes - len(data):
            self._error(f"output exceeds limit of {self.limits.max_output_bytes} bytes")
        self._buffer.extend(data)

    def _pack(self, format_string: str, value: object, label: str) -> bytes:
        try:
            return struct.pack(format_string, value)
        except (struct.error, OverflowError, TypeError):
            self._error(f"{label} {_PACK_RANGE_TEXT.get(format_string, 'cannot be encoded')}")

    def _write_int32(self, value: object, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            self._error(f"{label} must be a 32-bit integer")
        self._append(self._pack("<i", value, label))

    def _write_uint32(self, value: object, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            self._error(f"{label} must be an unsigned 32-bit integer")
        self._append(self._pack("<I", value, label))

    def _write_bool(self, value: object, label: str) -> None:
        if not isinstance(value, bool):
            self._error(f"{label} must be a boolean")
        self._append(b"\x01" if value else b"\x00")

    def _write_float32(self, value: object, label: str) -> None:
        if not isinstance(value, float):
            self._error(f"{label} must be a float")
        self._append(self._pack("<f", value, label))

    def _write_string(self, value: object, label: str = "string") -> None:
        if not isinstance(value, str):
            self._error(f"{label} must be a string")
        try:
            raw = value.encode("utf-16-le", errors="surrogatepass")
        except UnicodeError:
            self._error(f"{label} contains text that cannot be stored as UTF-16")

        code_units = len(raw) // 2
        if code_units > self.limits.max_string_code_units:
            self._error(
                f"{label} length {code_units} exceeds limit of "
                f"{self.limits.max_string_code_units} code units"
            )
        if code_units > 0xFFFFFFFF:
            self._error(f"{label} is too long for a 32-bit code-unit count")

        self._append(struct.pack("<I", code_units) + raw)

    def _write_vector[T](
        self,
        label: str,
        values: Sequence[T],
        callback: Callable[[T], None],
    ) -> None:
        try:
            count = len(values)
        except TypeError:
            self._error(f"{label} must be a sized sequence")

        if count > self.limits.max_vector_elements:
            self._error(
                f"{label} length {count} exceeds limit of "
                f"{self.limits.max_vector_elements} elements"
            )
        if count > 0xFFFFFFFF:
            self._error(f"{label} is too long for a 32-bit element count")

        with self.at_path(label):
            self._write_uint32(count, f"{label} length")
            for index, value in enumerate(values):
                with self.at_path(index):
                    callback(value)

    def _claim_node(self, kind: str) -> None:
        message = self._nodes.claim(kind)
        if message is not None:
            self._error(message)

    @contextmanager
    def _recursive(self, kind: str) -> Iterator[None]:
        if self._recursion_depth >= self.limits.max_recursion_depth:
            self._error(
                f"recursion depth limit of {self.limits.max_recursion_depth} "
                f"exceeded while writing {kind}"
            )
        self._recursion_depth += 1
        try:
            yield
        finally:
            self._recursion_depth -= 1

    def _require_resolved(
        self,
        metadata: object,
        label: str,
        *,
        raw_reference: bool = False,
    ) -> None:
        if self.reject_unresolved and metadata is None and not raw_reference:
            self._error(f"{label} has no resolved metadata")

    def _write_value(self, value: object) -> None:
        value = self._require_instance(value, Value, "value")
        self._claim_node("value")
        value_type = value.type
        if not isinstance(value_type, ValueType):
            self._error("value has an unsupported type")
        self._write_int32(int(value_type), "value type")

        if value_type is ValueType.INVALID:
            if value.value is not None:
                self._error("invalid values cannot carry a payload")
        elif value_type is ValueType.INT:
            if isinstance(value.value, bool) or not isinstance(value.value, int):
                self._error("int values require an integer payload")
            self._write_int32(value.value, "int value")
        elif value_type is ValueType.BOOL:
            self._write_bool(value.value, "bool value")
        elif value_type is ValueType.FLOAT:
            if value.binary32_bits is not None:
                self._append(self._pack("<I", value.binary32_bits, "float bits"))
            else:
                self._write_float32(value.value, "float value")
        elif value_type is ValueType.STRING:
            self._write_string(value.value, "string value")
        else:
            self._error(f"unsupported value type id {int(value_type)}")

    def _write_expression(self, expression: object) -> None:
        expression = self._require_instance(expression, Expression, "expression")
        self._claim_node("expression")
        with self._recursive("expression"):
            self._write_int32(int(expression.return_type), "expression return type")
            self._write_int32(expression.id, "expression id")

            if expression.id == EXPR_CONSTANT:
                if expression.constant is None:
                    self._error("constant expressions require a Value payload")
                with self.at_path("constant"):
                    self._write_value(expression.constant)
            elif expression.id == EXPR_VAR:
                self._write_string(expression.variable_name, "variable expression name")
            elif expression.id == EXPR_NAMEDCONSTANT:
                named_constant = expression.named_constant
                if not isinstance(named_constant, NamedConstantRef):
                    self._error("named-constant expressions require a named constant reference")
                if (
                    named_constant.value_type != expression.return_type
                    and not expression.raw_reference
                ):
                    self._error("named constant type does not match expression return type")
                self._require_resolved(
                    expression.metadata,
                    "expression reference",
                    raw_reference=expression.raw_reference,
                )
                self._require_resolved(
                    named_constant.metadata,
                    "named constant reference",
                    raw_reference=named_constant.raw_reference,
                )
                self._write_int32(named_constant.id, "named constant id")
            else:
                self._write_vector(
                    "parameters",
                    expression.parameters,
                    self._write_expression,
                )

            self._require_resolved(
                expression.metadata,
                "expression reference",
                raw_reference=expression.raw_reference,
            )

    def _write_event(self, event: object) -> None:
        event = self._require_instance(event, Event, "event")
        self._claim_node("event")
        self._require_resolved(
            event.metadata,
            "event reference",
            raw_reference=event.raw_reference,
        )
        self._write_int32(event.id, "event id")
        self._write_vector("parameters", event.parameters, self._write_expression)

    def _write_action(self, action: object) -> None:
        action = self._require_instance(action, ActionCall, "action")
        self._claim_node("action")
        self._require_resolved(
            action.metadata,
            "action reference",
            raw_reference=action.raw_reference,
        )
        self._write_int32(action.id, "action id")
        self._write_vector("parameters", action.parameters, self._write_expression)

    def _write_gui_action(self, gui_action: object) -> None:
        gui_action = self._require_instance(gui_action, GuiAction, "GUI action")
        self._claim_node("GUI action")
        with self._recursive("GUI action"):
            with self.at_path("action"):
                self._write_action(gui_action.action)
            self._write_vector("children", gui_action.children, self._write_gui_action)

    def _write_variable(self, variable: object) -> None:
        variable = self._require_instance(variable, Variable, "variable")
        self._claim_node("variable")
        self._write_int32(int(variable.type), "variable type")
        self._write_string(variable.name, "variable name")
        with self.at_path("default_expression"):
            self._write_expression(variable.default_expression)

    def _write_global_variable(self, variable: object) -> None:
        variable = self._require_instance(variable, GlobalVariable, "global variable")
        self._claim_node("global variable")
        self._write_int32(int(variable.type), "global variable type")
        self._write_string(variable.name, "global variable name")
        with self.at_path("default_value"):
            self._write_value(variable.default_value)
        with self.at_path("current_value"):
            self._write_value(variable.current_value)
        self._write_bool(variable.initialized, "global variable initialized")

    def _write_trigger(self, trigger: object) -> None:
        trigger = self._require_instance(trigger, Trigger, "trigger")
        self._claim_node("trigger")
        self._write_string(trigger.name, "trigger name")
        self._write_vector("events", trigger.events, self._write_event)
        self._write_vector("variables", trigger.variables, self._write_variable)
        self._write_vector("gui_actions", trigger.gui_actions, self._write_gui_action)

    def _write_module(self, module: object) -> None:
        module = self._require_instance(module, Module, "module")
        self._claim_node("module")
        self._write_string(module.name, "module name")
        self._write_string(module.description, "module description")
        self._write_vector("triggers", module.triggers, self._write_trigger)
        self._write_vector("globals", module.globals, self._write_global_variable)
        self._write_vector("dependencies", module.dependencies, self._write_string)

    def write_module(self, module: Module) -> bytes:
        """Encode one module and return its exact serialized bytes."""

        self._reset()
        self._write_module(module)
        return bytes(self._buffer)


def encode_module(
    module: Module,
    *,
    limits: WriterLimits | None = None,
    reject_unresolved: bool = False,
) -> bytes:
    """Encode a module using the verified raw AAUnlimited layout."""

    return BinaryWriter(
        limits,
        reject_unresolved=reject_unresolved,
    ).write_module(module)


write_module = encode_module
