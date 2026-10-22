"""Shape checks shared by the model constructors and ``from_ir`` readers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast

from .types import ModelError, TypeId, ValueType


def require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    return value


def coerce_type_id(value: object, label: str = "type") -> TypeId:
    raw = require_int(value, label)
    try:
        return ValueType(raw)
    except ValueError:
        return raw


def coerce_value_type(value: object) -> ValueType:
    type_id = coerce_type_id(value)
    if not isinstance(type_id, ValueType) or type_id is ValueType.N_TYPES:
        raise ModelError(f"unsupported Value type id: {type_id}")
    return type_id


def require_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def optional_text(value: object, label: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{label} must be a string or None")
    return value


def as_tuple[T](values: Iterable[T], label: str) -> tuple[T, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be an iterable of values")
    return tuple(values)


def require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return cast(Mapping[str, Any], value)


def require_field(data: Mapping[str, Any], name: str) -> Any:
    try:
        return data[name]
    except KeyError as exc:
        raise ModelError(f"missing model field: {name}") from exc
