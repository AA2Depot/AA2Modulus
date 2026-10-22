"""Bounded decoder for the AAUnlimited module binary format."""

from __future__ import annotations

import struct
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import NoReturn, cast

from ..core.diagnostics import format_path
from ..core.locations import BinaryLocation
from ..model.float32 import is_unusual_float32_bits
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
from ..model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, ModelError, ValueType
from ..model.values import Value
from .codec import NodeBudget, check_limit_fields


@dataclass(frozen=True, slots=True)
class ReaderLimits:
    """Limits applied before the decoder allocates or recurses."""

    max_string_code_units: int = 1_048_576
    max_vector_elements: int = 1_000_000
    max_recursion_depth: int = 256
    max_decoded_nodes: int = 1_000_000
    max_input_bytes: int = 67_108_864

    def __post_init__(self) -> None:
        check_limit_fields(self)


class DecodeError(ValueError):
    """A malformed binary input or violated decoder limit."""

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
        return f"{self.message} at offset 0x{self.offset:X} (path {format_path(self.path)})"


@dataclass(frozen=True, slots=True)
class TrailingBytes:
    """The unconsumed suffix of an otherwise decodable module."""

    offset: int
    count: int

    def __post_init__(self) -> None:
        if isinstance(self.offset, bool) or not isinstance(self.offset, int):
            raise TypeError("trailing-byte offset must be an integer")
        if isinstance(self.count, bool) or not isinstance(self.count, int):
            raise TypeError("trailing-byte count must be an integer")
        if self.offset < 0 or self.count <= 0:
            raise ValueError("trailing-byte values are out of range")


@dataclass(frozen=True, slots=True)
class DecodeResult:
    """Decoded module plus an optional trailing-byte warning."""

    module: Module
    trailing_bytes: TrailingBytes | None = None

    @property
    def has_trailing_bytes(self) -> bool:
        return self.trailing_bytes is not None


class BinaryReader:
    """Read one bounded AAUnlimited module from an in-memory byte sequence."""

    def __init__(
        self, data: bytes | bytearray | memoryview, limits: ReaderLimits | None = None
    ) -> None:
        self.limits = limits if limits is not None else ReaderLimits()
        if not isinstance(self.limits, ReaderLimits):
            raise TypeError("limits must be a ReaderLimits instance")

        try:
            view = memoryview(data)
        except TypeError as exc:
            raise TypeError("module data must be bytes-like") from exc

        if view.nbytes > self.limits.max_input_bytes:
            raise DecodeError(
                f"input exceeds limit of {self.limits.max_input_bytes} bytes",
                offset=0,
                path=(),
            )

        try:
            self.data = view.cast("B")
        except TypeError:
            self.data = memoryview(view.tobytes())

        self.pos = 0
        self._path: list[str | int] = []
        self._recursion_depth = 0
        self._nodes = NodeBudget(self.limits.max_decoded_nodes, "decoded", "reading")

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

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
        raise DecodeError(
            message,
            offset=self.pos if offset is None else offset,
            path=self.path if path is None else path,
        )

    def _require(self, size: int) -> None:
        if size < 0 or size > self.remaining:
            self._error(f"unexpected end of input; need {size} bytes")

    def raw(self, size: int) -> bytes:
        self._require(size)
        start = self.pos
        self.pos += size
        return self.data[start : self.pos].tobytes()

    def read_uint32(self) -> int:
        return cast(int, struct.unpack("<I", self.raw(4))[0])

    def read_int32(self) -> int:
        return cast(int, struct.unpack("<i", self.raw(4))[0])

    def read_bool(self) -> bool:
        return self.raw(1)[0] != 0

    def read_float32_bits(self) -> int:
        return cast(int, struct.unpack("<I", self.raw(4))[0])

    def read_string(self) -> str:
        length_offset = self.pos
        length = self.read_uint32()
        if length > self.limits.max_string_code_units:
            self._error(
                f"string length {length} exceeds limit of "
                f"{self.limits.max_string_code_units} code units",
                offset=length_offset,
            )

        if length > self.remaining // 2:
            self._error(
                f"truncated UTF-16LE string of {length} code units",
                offset=length_offset,
            )

        raw = self.raw(length * 2)
        return raw.decode("utf-16-le", errors="surrogatepass")

    def read_vector[T](
        self,
        label: str,
        callback: Callable[[], T],
        *,
        minimum_element_bytes: int = 0,
    ) -> tuple[T, ...]:
        with self.at_path(label):
            count_offset = self.pos
            count = self.read_uint32()
            if count > self.limits.max_vector_elements:
                self._error(
                    f"vector length {count} exceeds limit of "
                    f"{self.limits.max_vector_elements} elements",
                    offset=count_offset,
                )

            if minimum_element_bytes < 0:
                raise ValueError("minimum_element_bytes cannot be negative")
            if minimum_element_bytes and count > self.remaining // minimum_element_bytes:
                self._error(
                    f"vector length {count} cannot fit in the remaining input",
                    offset=count_offset,
                )

            values: list[T] = []
            for index in range(count):
                with self.at_path(index):
                    values.append(callback())
            return tuple(values)

    def _claim_node(self, kind: str, offset: int) -> None:
        message = self._nodes.claim(kind)
        if message is not None:
            self._error(message, offset=offset)

    @contextmanager
    def _recursive(self, kind: str, offset: int) -> Iterator[None]:
        if self._recursion_depth >= self.limits.max_recursion_depth:
            self._error(
                f"recursion depth limit of {self.limits.max_recursion_depth} "
                f"exceeded while reading {kind}",
                offset=offset,
            )
        self._recursion_depth += 1
        try:
            yield
        finally:
            self._recursion_depth -= 1

    def _location(self, offset: int) -> BinaryLocation:
        return BinaryLocation(offset, self.path)

    def _read_value(self) -> Value:
        node_offset = self.pos
        self._claim_node("value", node_offset)
        type_offset = self.pos
        value_type_id = self.read_int32()

        payload: int | bool | float | str | None
        float_binary_bits: int | None = None
        if value_type_id == ValueType.INVALID:
            payload = None
        elif value_type_id == ValueType.INT:
            with self.at_path("value"):
                payload = self.read_int32()
        elif value_type_id == ValueType.BOOL:
            with self.at_path("value"):
                payload = self.read_bool()
        elif value_type_id == ValueType.FLOAT:
            with self.at_path("value"):
                float_bits = self.read_float32_bits()
                payload = struct.unpack("<f", struct.pack("<I", float_bits))[0]
                if is_unusual_float32_bits(float_bits):
                    float_binary_bits = float_bits
        elif value_type_id == ValueType.STRING:
            with self.at_path("value"):
                payload = self.read_string()
        else:
            self._error(
                f"unknown Value type id {value_type_id}",
                offset=type_offset,
            )

        try:
            value_type = ValueType(value_type_id)
            return Value(
                value_type,
                payload,
                binary32_bits=float_binary_bits,
                binary_location=self._location(node_offset),
            )
        except (ModelError, TypeError) as exc:
            self._error(str(exc), offset=node_offset)

    def _read_expression(self) -> Expression:
        node_offset = self.pos
        self._claim_node("expression", node_offset)
        with self._recursive("expression", node_offset):
            with self.at_path("return_type"):
                return_type = self.read_int32()
            with self.at_path("id"):
                expression_id = self.read_int32()

            constant = None
            variable_name = None
            named_constant = None
            parameters: tuple[Expression, ...] = ()

            if expression_id == EXPR_CONSTANT:
                with self.at_path("constant"):
                    constant = self._read_value()
            elif expression_id == EXPR_VAR:
                with self.at_path("variable_name"):
                    variable_name = self.read_string()
            elif expression_id == EXPR_NAMEDCONSTANT:
                named_id_offset = self.pos
                with self.at_path("named_constant_id"):
                    named_id = self.read_int32()
                named_constant = NamedConstantRef(
                    return_type,
                    named_id,
                    binary_location=BinaryLocation(
                        named_id_offset,
                        (*self.path, "named_constant_id"),
                    ),
                )
            else:
                parameters = self.read_vector(
                    "parameters",
                    self._read_expression,
                    minimum_element_bytes=8,
                )

            try:
                return Expression(
                    return_type,
                    expression_id,
                    constant=constant,
                    variable_name=variable_name,
                    named_constant=named_constant,
                    parameters=parameters,
                    binary_location=self._location(node_offset),
                )
            except (ModelError, TypeError) as exc:
                self._error(str(exc), offset=node_offset)

    def _read_event(self) -> Event:
        node_offset = self.pos
        self._claim_node("event", node_offset)
        with self.at_path("id"):
            event_id = self.read_int32()
        parameters = self.read_vector(
            "parameters",
            self._read_expression,
            minimum_element_bytes=8,
        )
        try:
            return Event(event_id, parameters, binary_location=self._location(node_offset))
        except (ModelError, TypeError) as exc:
            self._error(str(exc), offset=node_offset)

    def _read_action(self) -> ActionCall:
        node_offset = self.pos
        self._claim_node("action", node_offset)
        with self.at_path("id"):
            action_id = self.read_int32()
        parameters = self.read_vector(
            "parameters",
            self._read_expression,
            minimum_element_bytes=8,
        )
        try:
            return ActionCall(action_id, parameters, binary_location=self._location(node_offset))
        except (ModelError, TypeError) as exc:
            self._error(str(exc), offset=node_offset)

    def _read_gui_action(self) -> GuiAction:
        node_offset = self.pos
        self._claim_node("GUI action", node_offset)
        with self._recursive("GUI action", node_offset):
            with self.at_path("action"):
                action = self._read_action()
            children = self.read_vector(
                "children",
                self._read_gui_action,
                minimum_element_bytes=12,
            )
            try:
                return GuiAction(
                    action,
                    children,
                    binary_location=self._location(node_offset),
                )
            except (ModelError, TypeError) as exc:
                self._error(str(exc), offset=node_offset)

    def _read_variable(self) -> Variable:
        node_offset = self.pos
        self._claim_node("variable", node_offset)
        with self.at_path("type"):
            variable_type = self.read_int32()
        with self.at_path("name"):
            name = self.read_string()
        with self.at_path("default_expression"):
            default_expression = self._read_expression()
        try:
            return Variable(
                variable_type,
                name,
                default_expression,
                binary_location=self._location(node_offset),
            )
        except (ModelError, TypeError) as exc:
            self._error(str(exc), offset=node_offset)

    def _read_global_variable(self) -> GlobalVariable:
        node_offset = self.pos
        self._claim_node("global variable", node_offset)
        with self.at_path("type"):
            variable_type = self.read_int32()
        with self.at_path("name"):
            name = self.read_string()
        with self.at_path("default_value"):
            default_value = self._read_value()
        with self.at_path("current_value"):
            current_value = self._read_value()
        with self.at_path("initialized"):
            initialized = self.read_bool()
        try:
            return GlobalVariable(
                variable_type,
                name,
                default_value,
                current_value,
                initialized,
                binary_location=self._location(node_offset),
            )
        except (ModelError, TypeError) as exc:
            self._error(str(exc), offset=node_offset)

    def _read_trigger(self) -> Trigger:
        node_offset = self.pos
        self._claim_node("trigger", node_offset)
        with self.at_path("name"):
            name = self.read_string()
        events = self.read_vector(
            "events",
            self._read_event,
            minimum_element_bytes=8,
        )
        variables = self.read_vector(
            "variables",
            self._read_variable,
            minimum_element_bytes=16,
        )
        gui_actions = self.read_vector(
            "gui_actions",
            self._read_gui_action,
            minimum_element_bytes=12,
        )
        try:
            return Trigger(
                name,
                events,
                variables,
                gui_actions,
                binary_location=self._location(node_offset),
            )
        except (ModelError, TypeError) as exc:
            self._error(str(exc), offset=node_offset)

    def _read_module(self) -> Module:
        node_offset = self.pos
        self._claim_node("module", node_offset)
        with self.at_path("name"):
            name = self.read_string()
        with self.at_path("description"):
            description = self.read_string()
        triggers = self.read_vector(
            "triggers",
            self._read_trigger,
            minimum_element_bytes=16,
        )
        globals_ = self.read_vector(
            "globals",
            self._read_global_variable,
            minimum_element_bytes=17,
        )
        dependencies = self.read_vector(
            "dependencies",
            self.read_string,
            minimum_element_bytes=4,
        )
        try:
            return Module(
                name,
                description,
                triggers,
                globals_,
                dependencies,
                binary_location=self._location(node_offset),
            )
        except (ModelError, TypeError) as exc:
            self._error(str(exc), offset=node_offset)

    def read_module(self) -> Module:
        with self.at_path("module"):
            return self._read_module()


def decode_module(
    data: bytes | bytearray | memoryview,
    *,
    limits: ReaderLimits | None = None,
    reject_trailing: bool = False,
) -> DecodeResult:
    """Decode a module and report any unconsumed suffix."""

    reader = BinaryReader(data, limits)
    module = reader.read_module()
    if reader.remaining == 0:
        return DecodeResult(module)

    trailing = TrailingBytes(reader.pos, reader.remaining)
    if reject_trailing:
        raise DecodeError(
            f"{trailing.count} trailing bytes remain after module",
            offset=trailing.offset,
            path=reader.path,
        )
    return DecodeResult(module, trailing)


def read_module(
    data: bytes | bytearray | memoryview,
    *,
    limits: ReaderLimits | None = None,
    reject_trailing: bool = False,
) -> Module:
    """Decode a module and return only the logical model."""

    return decode_module(
        data,
        limits=limits,
        reject_trailing=reject_trailing,
    ).module
