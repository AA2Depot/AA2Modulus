"""Stable source-name normalization shared by metadata and formatting."""

from __future__ import annotations

import re

_SOURCE_RESERVED = frozenset(
    {
        "bool",
        "break",
        "card",
        "compile",
        "const",
        "constant",
        "continue",
        "current",
        "default",
        "depends_on",
        "description",
        "else",
        "elseif",
        "event",
        "false",
        "float",
        "float_bits",
        "for",
        "from",
        "global",
        "if",
        "initialized",
        "import",
        "int",
        "invalid",
        "let",
        "loop",
        "macro",
        "module",
        "named_constant",
        "on",
        "parameters",
        "param",
        "raw_action",
        "raw_event",
        "raw_expression",
        "string",
        "slot",
        "to",
        "true",
        "trigger",
        "type",
        "validate",
        "var",
        "variable",
    }
)


def source_identifier(value: str) -> str:
    """Turn metadata display text into a stable source identifier."""

    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) and value.casefold() not in _SOURCE_RESERVED:
        return value
    words = re.findall(r"[A-Za-z0-9]+", value)
    candidate = "".join(word[:1].upper() + word[1:] for word in words)
    if not candidate:
        candidate = {
            "+": "Add",
            "-": "Subtract",
            "*": "Multiply",
            "/": "Divide",
        }.get(value, "Expression")
    if candidate[0].isdigit():
        candidate = "Value" + candidate
    if candidate.casefold() in _SOURCE_RESERVED:
        candidate += "Value"
    return candidate


def is_source_name(value: str, *, allow_qualified: bool = True) -> bool:
    """Return whether *value* is an exact, non-keyword source name.

    Policy names are source spellings rather than metadata display labels, so
    they must not be normalized before use. Qualified names are flat built-in
    symbols; every component follows the same identifier and keyword rules.
    """

    if not isinstance(value, str) or not value:
        return False
    parts = value.split(".")
    if len(parts) > 1 and not allow_qualified:
        return False
    return all(
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) is not None
        and part.casefold() not in _SOURCE_RESERVED
        for part in parts
    )


def is_qualified_source_name(value: str) -> bool:
    """Return whether *value* is a valid dotted source name."""

    return "." in value and is_source_name(value)
