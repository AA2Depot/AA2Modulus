"""Serialized typed values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Unpack

from ._checks import coerce_value_type, require_field, require_mapping
from .float32 import float32_bits, float32_from_bits, is_unusual_float32, is_unusual_float32_bits
from .node import NodeAnnotations, SerializedNode
from .types import ModelError, ValuePayload, ValueType


@dataclass(frozen=True, slots=True, eq=False)
class Value(SerializedNode):
    """A serialized AAUnlimited value with a validated known type."""

    type: ValueType
    value: ValuePayload = None
    binary32_bits: int | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        value_type = coerce_value_type(self.type)
        object.__setattr__(self, "type", value_type)

        if value_type is not ValueType.FLOAT and self.binary32_bits is not None:
            raise ModelError("binary32 bits are only valid for float values")

        if value_type is ValueType.INVALID:
            if self.value is not None:
                raise ModelError("invalid values have no payload")
        elif value_type is ValueType.INT:
            if isinstance(self.value, bool) or not isinstance(self.value, int):
                raise ModelError("int values require an integer payload")
        elif value_type is ValueType.BOOL:
            if not isinstance(self.value, bool):
                raise ModelError("bool values require a boolean payload")
        elif value_type is ValueType.FLOAT:
            if not isinstance(self.value, float):
                raise ModelError("float values require a float payload")
            bits = (
                self.binary32_bits if self.binary32_bits is not None else float32_bits(self.value)
            )
            try:
                normalized = float32_from_bits(bits)
            except ValueError as exc:
                raise ModelError(str(exc)) from exc
            object.__setattr__(self, "value", normalized)
            object.__setattr__(
                self,
                "binary32_bits",
                bits if is_unusual_float32_bits(bits) else None,
            )
        elif value_type is ValueType.STRING and not isinstance(self.value, str):
            raise ModelError("string values require a string payload")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Value):
            return NotImplemented
        if self.type != other.type:
            return False
        if self.type is ValueType.FLOAT:
            assert isinstance(self.value, float)
            assert isinstance(other.value, float)
            self_bits = self.binary32_bits
            if self_bits is None:
                self_bits = float32_bits(self.value)
            other_bits = other.binary32_bits
            if other_bits is None:
                other_bits = float32_bits(other.value)
            return self_bits == other_bits
        return self.value == other.value

    def __hash__(self) -> int:
        if self.type is ValueType.FLOAT:
            assert isinstance(self.value, float)
            bits = self.binary32_bits
            if bits is None:
                bits = float32_bits(self.value)
            return hash((self.type, bits))
        return hash((self.type, self.value))

    @classmethod
    def invalid(cls, **locations: Unpack[NodeAnnotations]) -> Value:
        return cls(ValueType.INVALID, None, **locations)

    @classmethod
    def integer(cls, value: int, **locations: Unpack[NodeAnnotations]) -> Value:
        return cls(ValueType.INT, value, **locations)

    @classmethod
    def boolean(cls, value: bool, **locations: Unpack[NodeAnnotations]) -> Value:
        return cls(ValueType.BOOL, value, **locations)

    @classmethod
    def floating(cls, value: float, **locations: Unpack[NodeAnnotations]) -> Value:
        return cls(ValueType.FLOAT, value, **locations)

    @classmethod
    def floating_bits(cls, bits: int, **locations: Unpack[NodeAnnotations]) -> Value:
        return cls(ValueType.FLOAT, float32_from_bits(bits), binary32_bits=bits, **locations)

    @classmethod
    def string(cls, value: str, **locations: Unpack[NodeAnnotations]) -> Value:
        return cls(ValueType.STRING, value, **locations)

    def to_ir(self) -> dict[str, Any]:
        if self.type is ValueType.FLOAT:
            assert isinstance(self.value, float)
            if self.binary32_bits is not None or is_unusual_float32(self.value):
                bits = self.binary32_bits
                if bits is None:
                    bits = float32_bits(self.value)
                return {"type": int(self.type), "value": None, "float_bits": bits}
        return {"type": int(self.type), "value": self.value}

    @classmethod
    def from_ir(cls, data: Mapping[str, Any]) -> Value:
        data = require_mapping(data, "value IR")
        if data.get("type") == ValueType.FLOAT and "float_bits" in data:
            bits = require_field(data, "float_bits")
            return cls(
                ValueType.FLOAT,
                float32_from_bits(bits),
                binary32_bits=bits,
            )
        return cls(require_field(data, "type"), require_field(data, "value"))
