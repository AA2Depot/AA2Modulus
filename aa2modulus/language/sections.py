"""Readers for the per-target policy sections: names, visibility, defects and roles."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from ..metadata.identities import NativeKind, WireIdentity
from ..model.types import ValueType
from .fields import (
    TYPE_NAMES,
    check_keys,
    read_array,
    read_keyed_target,
    read_name,
    read_positive_int,
    read_scalar,
    read_scoped_key,
    read_string,
    read_table,
    read_wire,
)
from .values import EventValues


def read_parameter_names(
    value: Mapping[str, object],
) -> tuple[tuple[WireIdentity, tuple[str, ...]], ...]:
    result: list[tuple[WireIdentity, tuple[str, ...]]] = []
    for section, kind in (("actions", "action"), ("expressions", "expression")):
        label = f"policy.parameter_names.{section}"
        for raw_key, raw_names in read_table(value.get(section, {}), label).items():
            key_label = f"{label}.{raw_key}"
            target = read_keyed_target(cast(NativeKind, kind), raw_key, key_label)
            names = tuple(
                read_string(item, f"{key_label}[{index}]", nonempty=True)
                for index, item in enumerate(read_array(raw_names, key_label))
            )
            result.append((target, names))
    return tuple(result)


def read_parameter_roles(
    value: Mapping[str, object],
) -> tuple[tuple[WireIdentity, tuple[tuple[str, str], ...]], ...]:
    result: list[tuple[WireIdentity, tuple[tuple[str, str], ...]]] = []
    for section, kind in (("actions", "action"), ("expressions", "expression")):
        label = f"policy.parameter_roles.{section}"
        for raw_key, raw_roles in read_table(value.get(section, {}), label).items():
            key_label = f"{label}.{raw_key}"
            target = read_keyed_target(cast(NativeKind, kind), raw_key, key_label)
            roles = tuple(
                (name, read_string(role, f"{key_label}.{name}", nonempty=True))
                for name, role in read_table(raw_roles, key_label).items()
            )
            result.append((target, roles))
    return tuple(result)


def read_descriptions(value: Mapping[str, object]) -> tuple[tuple[WireIdentity, str], ...]:
    result: list[tuple[WireIdentity, str]] = []
    label = "policy.descriptions.expressions"
    for raw_key, raw_text in read_table(value.get("expressions", {}), label).items():
        key_label = f"{label}.{raw_key}"
        target = read_keyed_target("expression", raw_key, key_label)
        result.append((target, read_string(raw_text, key_label, nonempty=True).strip()))
    return tuple(result)


def read_preferred_names[T](
    value: object,
    parse_key: Callable[[object, str], T],
    label: str,
) -> tuple[tuple[T, str], ...]:
    return tuple(
        (parse_key(raw_key, f"{label}.{raw_key}"), read_name(raw_name, f"{label}.{raw_key}"))
        for raw_key, raw_name in read_table(value, label).items()
    )


def read_defects(
    value: object, label: str
) -> tuple[tuple[ValueType, int, tuple[ValueType, ...], str], ...]:
    result: list[tuple[ValueType, int, tuple[ValueType, ...], str]] = []
    for raw_key, raw_entry in read_table(value, label).items():
        item_label = f"{label}.{raw_key}"
        scope, identifier = read_scoped_key(raw_key, item_label)
        entry = read_table(raw_entry, item_label)
        check_keys(entry, {"declared", "reason"}, item_label, required={"declared", "reason"})
        declared: list[ValueType] = []
        for index, raw_type in enumerate(read_array(entry["declared"], f"{item_label}.declared")):
            type_label = f"{item_label}.declared[{index}]"
            parameter_type = TYPE_NAMES.get(raw_type) if isinstance(raw_type, str) else None
            if parameter_type is None:
                raise ValueError(f"{type_label} must be one of invalid, int, bool, float or string")
            declared.append(parameter_type)
        reason = read_string(entry["reason"], f"{item_label}.reason", nonempty=True)
        result.append((scope, identifier, tuple(declared), reason))
    return tuple(result)


def read_event_values(value: object, label: str) -> tuple[EventValues, ...]:
    result: list[EventValues] = []
    for raw_key, raw_entry in read_table(value, label).items():
        item_label = f"{label}.{raw_key}"
        target = read_wire("expression", raw_key, item_label)
        entry = read_table(raw_entry, item_label)
        check_keys(
            entry,
            {"callback", "otherwise", *(name for name in TYPE_NAMES if name != "invalid")},
            item_label,
            required={"callback", "otherwise"},
        )
        events = tuple(
            (
                TYPE_NAMES[name],
                read_targets(entry[name], read_positive_int, f"{item_label}.{name}"),
            )
            for name in TYPE_NAMES
            if name in entry
        )
        if not events:
            raise ValueError(f"{item_label}: list the events of at least one value type")
        result.append(
            EventValues(
                target,
                read_string(entry["callback"], f"{item_label}.callback", nonempty=True),
                events,
                read_scalar(entry["otherwise"], f"{item_label}.otherwise"),
            )
        )
    return tuple(result)


def read_roles(value: object, label: str) -> tuple[tuple[tuple[ValueType, int], str], ...]:
    return tuple(
        (
            read_scoped_key(raw_key, f"{label}.{raw_key}"),
            read_string(raw_role, f"{label}.{raw_key}", nonempty=True),
        )
        for raw_key, raw_role in read_table(value, label).items()
    )


def read_targets[T](
    value: object,
    parse_key: Callable[[object, str], T],
    label: str,
) -> tuple[T, ...]:
    result: list[T] = []
    for index, raw_key in enumerate(read_array(value, label)):
        item_label = f"{label}[{index}]"
        parsed = parse_key(raw_key, item_label)
        if parsed in result:
            raise ValueError(f"{item_label} lists {raw_key!r} more than once")
        result.append(parsed)
    return tuple(result)
