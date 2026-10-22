"""Deterministic fingerprints for immutable fact and source-policy inputs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import cast

from ..model.values import Value


def canonical_hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def input_data(value: object) -> object:
    """Exclude indexes and program locations; include all declared metadata inputs."""

    if isinstance(value, Value):
        return value.to_ir()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: input_data(getattr(value, item.name))
            for item in fields(value)
            if item.init and not item.name.startswith("_")
        }
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): input_data(item) for key, item in mapping.items()}
    if isinstance(value, (tuple, list)):
        return [input_data(item) for item in value]
    return value
