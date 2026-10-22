"""Shape checks for registry JSON documents; every failure is a MetadataError."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from .schema import MetadataError


def require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MetadataError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise MetadataError(f"{label} must have string keys")
    return cast(Mapping[str, object], value)


def require_array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise MetadataError(f"{label} must be an array")
    return cast(list[object], value)


def require_fields(
    value: Mapping[str, object],
    label: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    extra = set(value) - required - (optional or set())
    missing = required - set(value)
    if extra:
        raise MetadataError(f"{label}.{min(extra)} is an unknown field")
    if missing:
        raise MetadataError(f"{label}.{min(missing)} is required")


def require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetadataError(f"{label} must be an integer")
    return value


def require_int32(value: object, label: str) -> int:
    result = require_int(value, label)
    if not -(1 << 31) <= result < (1 << 31):
        raise MetadataError(f"{label} must fit a signed 32-bit integer")
    return result


def require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise MetadataError(f"{label} must be a string")
    return value


def require_digest(value: object, label: str) -> str:
    text = require_string(value, label)
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise MetadataError(f"{label} must be a lowercase SHA-256 digest")
    return text


def load_json(path: Path) -> Mapping[str, object]:
    try:
        raw: object = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise MetadataError(f"cannot read metadata file {path}: {exc}") from exc
    return require_mapping(raw, f"{path}.<root>")


def _unique_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON numeric constant {value!r}")
