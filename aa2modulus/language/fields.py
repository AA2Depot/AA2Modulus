"""Typed readers for TOML policy values; failures name the offending key."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import cast

from ..core.source_names import is_source_name
from ..metadata.identities import NativeKind, WireIdentity
from ..model.types import INT32_RANGE, ValueType
from ..model.values import Value

TYPE_NAMES = {item.name.lower(): item for item in ValueType if item is not ValueType.N_TYPES}
CANONICAL_ID = re.compile(r"(?:0|[1-9][0-9]*)\Z")


def read_table(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a table")
    return cast(Mapping[str, object], value)


def read_array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be an array")
    return cast(list[object], value)


def check_keys(
    value: Mapping[str, object],
    allowed: set[str],
    label: str,
    *,
    required: set[str] | frozenset[str] = frozenset(),
) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{label}: unknown key(s): {', '.join(sorted(unknown))}")
    missing = required - set(value)
    if missing:
        raise ValueError(f"{label}: missing required key(s): {', '.join(sorted(missing))}")


def read_string(value: object, label: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if nonempty and not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def read_name(value: object, label: str) -> str:
    name = read_string(value, label, nonempty=True)
    if not is_source_name(name):
        raise ValueError(f"{label} must be an exact non-keyword source name")
    return name


def read_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be positive")
    return value


def read_decimal(value: object, label: str) -> int:
    if not isinstance(value, str) or CANONICAL_ID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical decimal number")
    return int(value)


def read_id_key(value: object, label: str) -> int:
    result = read_decimal(value, label)
    if result < 1:
        raise ValueError(f"{label} must be positive")
    return result


def read_scoped_key(value: object, label: str) -> tuple[ValueType, int]:
    if not isinstance(value, str) or value.count(":") != 1:
        raise ValueError(f'{label} must use type:id syntax such as "int:10"')
    type_name, raw_id = value.split(":", 1)
    scope = TYPE_NAMES.get(type_name)
    if scope is None:
        raise ValueError(
            f"{label} has unknown type {type_name!r}; use invalid, int, bool, float or string"
        )
    return scope, read_id_key(raw_id, label)


def read_scalar(value: object, label: str) -> Value:
    """Convert a TOML scalar to a typed value; the TOML type selects the wire type."""

    if isinstance(value, bool):
        return Value.boolean(value)
    if isinstance(value, int):
        if value not in INT32_RANGE:
            raise ValueError(f"{label} must fit a signed 32-bit integer")
        return Value.integer(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number")
        try:
            return Value.floating(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{label}: {exc}") from exc
    if isinstance(value, str):
        return Value.string(value)
    raise TypeError(f"{label} must be a boolean, integer, float or string")


def read_keyed_target(kind: NativeKind, raw_key: str, label: str) -> WireIdentity:
    """A table key in target notation: ``108`` for actions and events, else ``"type:id"``."""

    if kind in ("action", "event"):
        return WireIdentity(kind, read_id_key(raw_key, label))
    return read_wire(kind, raw_key, label)


def read_wire(kind: NativeKind, value: object, label: str) -> WireIdentity:
    if kind in ("action", "event"):
        return WireIdentity(kind, read_positive_int(value, label))
    scope, identifier = read_scoped_key(value, label)
    if kind == "named_constant" and scope is ValueType.INVALID:
        raise ValueError(
            f"{label}: named constants require a concrete type (int, bool, float, string)"
        )
    return WireIdentity(kind, identifier, scope)
