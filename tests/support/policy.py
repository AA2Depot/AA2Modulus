"""Build and write TOML language-policy documents for tests.

The standard library reads TOML but cannot write it, so tests edit parsed
documents as dictionaries and serialize them with this small inline writer.
"""

from __future__ import annotations

import copy
import json
import math
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aa2modulus.context.operation import SourceContext
from aa2modulus.language.loader import language_policy_path, load_language_policy
from aa2modulus.metadata.loader import load_metadata


def default_policy_document() -> dict[str, Any]:
    """Return a fresh, mutable copy of the shipped policy document."""

    with language_policy_path().open("rb") as handle:
        return copy.deepcopy(tomllib.load(handle))


def policy_toml(document: Mapping[str, Any]) -> str:
    """Serialize a policy document; every root key becomes one inline value."""

    return "".join(f"{_key(key)} = {_value(value)}\n" for key, value in document.items())


def write_policy(path: Path, document: Mapping[str, Any]) -> Path:
    path.write_text(policy_toml(document), encoding="utf-8")
    return path


def edited_policy(tmp_path: Path, edit: Callable[[dict[str, Any]], None]) -> Path:
    """Write the default policy after ``edit`` mutates it in place."""

    document = default_policy_document()
    edit(document)
    return write_policy(tmp_path / "policy.toml", document)


def policy_context(path: Path) -> SourceContext:
    """A source context over the policy file at ``path`` instead of the shipped one."""

    metadata = load_metadata()
    return SourceContext(metadata, load_language_policy(metadata=metadata, path=path))


def _key(key: object) -> str:
    return _string(str(key))


def _string(value: str) -> str:
    # JSON basic-string escapes are valid TOML; TOML additionally forbids raw DEL.
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"TOML cannot represent {type(value).__name__}")
