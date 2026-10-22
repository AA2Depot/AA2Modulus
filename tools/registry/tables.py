"""The four native registry tables: actions, events, expressions and named constants

Each function reads its table from the pinned checkout and returns the
registry document written as ``<table>.json``.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from aa2modulus.metadata.schema import FILE_SCHEMAS, GENERATOR_VERSION

from . import cpp, source
from .source import TRIGGERS

ACTIONS = TRIGGERS + "Actions.cpp"
EVENTS = TRIGGERS + "Event.cpp"
EXPRESSIONS = TRIGGERS + "Expressions.cpp"
NAMED_CONSTANTS = TRIGGERS + "NamedConstant.cpp"


def actions(root: Path) -> dict[str, Any]:
    text = source.read(root, ACTIONS)
    headers = source.read(root, TRIGGERS + "Actions.h") + source.read(root, TRIGGERS + "Value.h")
    ids = cpp.enum(headers, "Actions")
    types = cpp.enum(headers, "Types")
    category_ids = cpp.enum(headers, "ActionCategories")
    categories = _categories(text, "g_ActionCategories", category_ids, "action")

    rows = {}
    for index, entry in enumerate(cpp.entries(cpp.initializer(text, "g_Actions"), "actions"), 1):
        _width(entry, 7, f"action registry entry {index}")
        identifier = _positional_id(entry, ids, index, "action")
        label = f"action {identifier}"

        row = _row(entry, index, identifier, category_ids, categories, label, ACTIONS)
        row["parameter_types"] = cpp.symbol_list(entry[5], types, f"{label} parameter")
        row["implementation"] = _implementation(entry[6], label)
        rows[str(identifier)] = row

    return _document("actions.json", categories, rows)


def events(root: Path) -> dict[str, Any]:
    text = source.read(root, EVENTS)
    headers = source.read(root, TRIGGERS + "Event.h") + source.read(root, TRIGGERS + "Value.h")
    ids = cpp.enum(headers, "Events")
    types = cpp.enum(headers, "Types")
    category_ids = cpp.enum(headers, "EventCategories")
    categories = _categories(text, "g_EventCategories", category_ids, "event")
    symbols = _names_by_value(ids)

    rows = {}
    for index, entry in enumerate(cpp.entries(cpp.initializer(text, "g_Events"), "events"), 1):
        _width(entry, 6, f"event registry entry {index}")
        identifier = _positional_id(entry, ids, index, "event")
        label = f"event {identifier}"

        row = _row(entry, index, identifier, category_ids, categories, label, EVENTS)
        row["symbol"] = symbols[identifier]
        row["parameter_types"] = cpp.symbol_list(entry[5], types, f"{label} parameter")
        rows[str(identifier)] = row

    return _document("events.json", categories, rows)


def expressions(root: Path) -> dict[str, Any]:
    text = source.read(root, EXPRESSIONS)
    headers = "".join(
        source.read(root, TRIGGERS + name) for name in ("Expressions.h", "Actions.h", "Value.h")
    )
    ids = cpp.enum(headers, "Expressions")
    types = cpp.enum(headers, "Types")
    category_ids = cpp.enum(headers, "ExpressionCategories")
    categories = _categories(text, "g_ExpressionCategories", category_ids, "expression")

    # Four LUA rows use ACTIONCAT_GENERAL, an exact alias of EXPRCAT_GENERAL.
    category_symbols = dict(category_ids)
    if "ACTIONCAT_GENERAL" in cpp.enum(headers, "ActionCategories"):
        category_symbols["ACTIONCAT_GENERAL"] = category_ids["EXPRCAT_GENERAL"]

    groups = cpp.grouped_entries(cpp.initializer(text, "g_Expressions"), "expressions")
    if len(groups) != types["N_TYPES"]:
        raise RuntimeError(f"expression type-group count {len(groups)} does not match N_TYPES")

    rows: dict[str, dict[str, Any]] = {}
    for type_id, (type_name, group) in enumerate(zip(_type_names(types), groups, strict=True)):
        for index, entry in enumerate(group, 1):
            _width(entry, 8, f"expression type {type_id} registry entry {index}")
            identifier = _positional_id(entry, ids, index, f"expression type {type_id}")
            label = f"expression {type_id}:{identifier}"

            row = _row(entry, index, identifier, category_symbols, categories, label, EXPRESSIONS)
            row["return_type"] = type_id
            row["return_type_name"] = type_name
            row["parameter_types"] = cpp.symbol_list(entry[5], types, f"{label} parameter")
            row["declared_return_type"] = cpp.symbol(entry[6], types, "expression return type")
            row["implementation"] = _implementation(entry[7], label)
            rows.setdefault(type_name, {})[str(identifier)] = row

    return _document("expressions.json", categories, rows)


def named_constants(root: Path) -> dict[str, Any]:
    text = source.read(root, NAMED_CONSTANTS)
    headers = source.read(root, TRIGGERS + "NamedConstant.h") + source.read(
        root, TRIGGERS + "Value.h"
    )
    types = cpp.enum(headers, "Types")
    category_ids = cpp.enum(headers, "NamedConstantCategories")
    categories = _categories(text, "g_NamedConstantCategories", category_ids, "named constant")
    enums = source.enum_values(root)

    groups = cpp.grouped_entries(cpp.initializer(text, "g_NamedConstants"), "named constants")
    if len(groups) != types["N_TYPES"]:
        raise RuntimeError(f"named-constant type-group count {len(groups)} does not match N_TYPES")

    # Constants keep list order and duplicate IDs; native lookup is explicit ID first.
    rows: dict[str, list[dict[str, Any]]] = {}
    for type_id, (type_name, group) in enumerate(zip(_type_names(types), groups, strict=True)):
        for index, entry in enumerate(group, 1):
            _width(entry, 6, f"named constant type {type_id} registry entry {index}")
            identifier = cpp.symbol(entry[0], {}, "named constant id")
            label = f"named constant {type_id}:{identifier}"

            row = _row(entry, index, identifier, category_ids, categories, label, NAMED_CONSTANTS)
            row["value_type"] = type_id
            row["value_type_name"] = type_name
            row["value"], expression = _constant_value(entry[5], type_id, f"{label} value")

            if expression is None:
                row["resolved_value"] = row["value"]
            elif expression in enums:
                row["value_expression"] = expression
                row["resolved_value"] = {"type": type_id, "value": enums[expression]}
            else:
                raise RuntimeError(f"{label}: unsupported enum value expression {expression!r}")

            rows.setdefault(type_name, []).append(row)

    return _document("named_constants.json", categories, rows)


# Shared row parts


def _width(entry: cpp.Entry, expected: int, label: str) -> None:
    if len(entry) != expected:
        raise RuntimeError(f"{label} has {len(entry)} fields, expected {expected}")


def _positional_id(entry: cpp.Entry, ids: dict[str, int], index: int, label: str) -> int:
    """Actions, events and expressions are registered in ID order, starting at 1."""

    identifier = cpp.symbol(entry[0], ids, f"{label} id")
    if identifier != index:
        raise RuntimeError(f"{label} registry position {index} has explicit id {identifier}")
    return identifier


def _row(
    entry: cpp.Entry,
    index: int,
    identifier: int,
    category_ids: dict[str, int],
    categories: list[str],
    label: str,
    file: str,
) -> dict[str, Any]:
    """Fields every table shares: ID, category, the three texts and provenance."""

    category = cpp.symbol(entry[1], category_ids, f"{label} category")
    if not 0 <= category < len(categories):
        raise RuntimeError(f"{label} has out-of-range category {category}")

    registration = "\n".join(entry).encode("utf-8")
    return {
        "id": identifier,
        "registry_index": index,
        "category_id": category,
        "category": categories[category],
        "name": cpp.string(entry[2], f"{label} name"),
        "interactive_name": cpp.string(entry[3], f"{label} interactive name"),
        "description": cpp.string(entry[4], f"{label} description"),
        "provenance": {
            "source_file": file,
            "registration_sha256": hashlib.sha256(registration).hexdigest(),
        },
    }


def _categories(text: str, anchor: str, ids: dict[str, int], label: str) -> list[str]:
    names = [
        cpp.string(part, f"{label} category")
        for part in cpp.split(cpp.initializer(text, anchor))
        if cpp.clean(part)
    ]

    expected = max((value for key, value in ids.items() if not key.endswith("_N")), default=-1) + 1
    if len(names) != expected:
        raise RuntimeError(f"{label} category count {len(names)} does not match enum {expected}")

    return names


def _implementation(field: str, label: str) -> str | None:
    """The callback ``&Thread::Name`` as ``Thread::Name``; NULL for payload markers."""

    pointer = cpp.clean(field)
    if pointer == "NULL":
        return None
    if re.fullmatch(r"&Thread::[A-Za-z_]\w*", pointer):
        return pointer.removeprefix("&")
    raise RuntimeError(f"{label}: unsupported callback {pointer!r}")


def _constant_value(
    field: str, type_id: int, label: str
) -> tuple[dict[str, Any] | None, str | None]:
    """``Value(...)`` as a literal value, or as the enum expression it names."""

    value = cpp.clean(field)
    opening = value.find("(")
    if not value.startswith("Value") or opening < 0:
        raise RuntimeError(f"{label} does not contain a Value constructor")

    closing = cpp.matching(value, opening)
    if value[closing + 1 :].strip():
        raise RuntimeError(f"{label} has trailing text after Value constructor")

    inner = cpp.clean(value[opening + 1 : closing])
    if inner in ("true", "false"):
        return {"type": type_id, "value": inner == "true"}, None
    if re.fullmatch(r"[-+]?\d+", inner):
        return {"type": type_id, "value": int(inner, 10)}, None
    if re.fullmatch(r"0[xX][0-9A-Fa-f]+", inner):
        return {"type": type_id, "value": int(inner, 16)}, None
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][-+]?\d+)?[fF]?", inner):
        return {"type": type_id, "value": float(inner.rstrip("fF"))}, None
    if '"' in inner:
        return {"type": type_id, "value": cpp.string(inner, label)}, None

    return None, inner


def _names_by_value(ids: dict[str, int]) -> dict[int, str]:
    names: dict[int, str] = {}
    for name, value in ids.items():
        names.setdefault(value, name)
    return names


def _type_names(types: dict[str, int]) -> list[str]:
    """``int``, ``bool``... for each value type in ID order."""

    names = _names_by_value(types)
    return [names[type_id].removeprefix("TYPE_").lower() for type_id in range(types["N_TYPES"])]


def _document(file: str, categories: list[str], entries: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": FILE_SCHEMAS[file],
        "source_revision": source.REVISION,
        "generator_version": GENERATOR_VERSION,
        "categories": [{"id": index, "name": name} for index, name in enumerate(categories)],
        "entries": entries,
    }
