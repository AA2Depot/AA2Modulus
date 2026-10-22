"""Source text primitives for the formatter: quoting, type names and literals."""

from __future__ import annotations

import json

from ...model.float32 import float32_bits, is_unusual_float32
from ...model.types import TypeId, ValueType
from ...model.values import Value


class FormatError(ValueError):
    """Raised when a serialized node cannot be represented by unified syntax."""


def quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def type_name(value: TypeId) -> str:
    try:
        return {
            ValueType.INVALID: "invalid",
            ValueType.INT: "int",
            ValueType.BOOL: "bool",
            ValueType.FLOAT: "float",
            ValueType.STRING: "string",
        }[ValueType(value)]
    except (KeyError, ValueError):
        return f"type {value}"


def declaration_type(value: TypeId, kind: str, name: str) -> str:
    try:
        value_type = ValueType(value)
    except ValueError:
        raise FormatError(
            f"{kind} {name!r} has a type ID that source validation cannot represent"
        ) from None
    if value_type not in {
        ValueType.INT,
        ValueType.BOOL,
        ValueType.FLOAT,
        ValueType.STRING,
    }:
        raise FormatError(f"{kind} {name!r} has a type that source validation cannot represent")
    return type_name(value_type)


def literal(value: Value) -> str:
    if value.type is ValueType.INVALID:
        raise FormatError("invalid value requires explicit raw syntax")
    if value.type is ValueType.STRING:
        assert isinstance(value.value, str)
        return quote(value.value)
    if value.type is ValueType.BOOL:
        return "true" if value.value else "false"
    if value.type is ValueType.FLOAT:
        assert isinstance(value.value, float)
        bits = value.binary32_bits if value.binary32_bits is not None else float32_bits(value.value)
        if is_unusual_float32(value.value):
            return f"float_bits(0x{bits:08x})"
    return str(value.value)


def raw_value(value: Value) -> str:
    if value.type is ValueType.INVALID:
        return "invalid"
    return literal(value)
