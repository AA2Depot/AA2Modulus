"""Shared human-facing formatting helpers for diagnostics and source output."""

from __future__ import annotations

import json

from .float32 import float32_bits, is_unusual_float32
from .types import TypeId, ValueType
from .values import Value

_TYPE_NAMES = {
    ValueType.INVALID: "invalid",
    ValueType.INT: "int",
    ValueType.BOOL: "bool",
    ValueType.FLOAT: "float",
    ValueType.STRING: "string",
}


def type_name(value: TypeId, *, unknown_style: str = "hash") -> str:
    """Render a type ID consistently across validation and inspection output."""

    try:
        value_type = ValueType(value)
    except ValueError:
        return f"type {value}" if unknown_style == "space" else f"type#{value}"
    return _TYPE_NAMES.get(value_type, f"type {int(value_type)}")


def value_text(value: Value) -> str:
    """Render a serialized value for inspection output."""

    if value.type is ValueType.INVALID:
        return "invalid"
    if value.type is ValueType.BOOL:
        return "true" if value.value else "false"
    if value.type is ValueType.STRING:
        return json.dumps(value.value, ensure_ascii=True)
    if value.type is ValueType.FLOAT:
        assert isinstance(value.value, float)
        if is_unusual_float32(value.value):
            bits = value.binary32_bits
            if bits is None:
                bits = float32_bits(value.value)
            return f"float_bits(0x{bits:08x})"
    return str(value.value)


def replace_parameters(template: str, parameters: tuple[str, ...]) -> str:
    """Replace AAUnlimited's sequential ``%p`` placeholders."""

    result = template
    for parameter in parameters:
        result = result.replace("%p", parameter, 1)
    return result
