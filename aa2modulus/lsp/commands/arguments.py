"""Validation of the JSON object arguments a command receives."""

from __future__ import annotations

from collections.abc import Mapping

from pygls.exceptions import JsonRpcInvalidParams

from ..protocol.uris import file_identity


def object_argument(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise JsonRpcInvalidParams("The command requires one object argument")
    return value


def file_argument(payload: Mapping[str, object], key: str) -> str:
    uri = payload.get(key)
    if not isinstance(uri, str) or (identity := file_identity(uri)) is None:
        raise JsonRpcInvalidParams(f"{key} must be a local file URI")
    return identity
