"""Strict reader for the editable TOML source-language policy.

The file holds authored choices only. Signatures, operator syntax and literal
row identities are copied from the registry and the fixed grammar while the
policy is read; ``LanguagePolicy.validate`` then checks every choice
against the same registry.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from ..core.source_names import is_qualified_source_name, is_source_name
from ..metadata.identities import NativeKind, RowIdentity
from ..metadata.snapshot import MetadataSnapshot
from ..model.native import ActionMetadata, ExpressionMetadata
from ..model.types import ValueType
from .fields import (
    check_keys,
    read_array,
    read_decimal,
    read_id_key,
    read_keyed_target,
    read_positive_int,
    read_scalar,
    read_scoped_key,
    read_string,
    read_table,
)
from .operators import OPERATOR_SYNTAX, OperatorDefinition
from .policy import LanguagePolicy
from .sections import (
    read_defects,
    read_descriptions,
    read_event_values,
    read_parameter_names,
    read_parameter_roles,
    read_preferred_names,
    read_roles,
    read_targets,
)
from .validation.identities import describe
from .values import (
    ActionDefault,
    MemberArgument,
    MemberForm,
    SourceValue,
)

_ROOT_FIELDS = {
    "language_version",
    "protected_names",
    "acknowledgeable",
    "operators",
    "action_defaults",
    "preferred_names",
    "readable",
    "defects",
    "event_values",
    "result_roles",
    "literals",
    "members",
    "parameter_names",
    "parameter_roles",
    "descriptions",
}


def read_source_policy(path: str | Path, metadata: MetadataSnapshot) -> LanguagePolicy:
    """Read a TOML policy file and resolve it against ``metadata``."""

    payload = Path(path).read_bytes()
    document = tomllib.loads(payload.decode("utf-8"))
    return source_policy_from_document(document, metadata)


def source_policy_from_document(
    document: Mapping[str, object],
    metadata: MetadataSnapshot,
) -> LanguagePolicy:
    """Build policy from a parsed TOML document, copying derived facts from ``metadata``.

    Sections are read in a fixed order, so a document with several errors
    always reports the same first one.
    """

    root = read_table(document, "policy")
    check_keys(root, _ROOT_FIELDS, "policy", required={"language_version"})
    language_version = read_positive_int(root["language_version"], "policy.language_version")
    sections = {name: _section(root, name, keys) for name, keys in _SECTIONS}
    readable = sections["readable"]
    defects = sections["defects"]
    event_values = sections["event_values"]
    result_roles = sections["result_roles"]

    operators = _operators(root.get("operators", {}), metadata)
    action_defaults = _action_defaults(root.get("action_defaults", {}))
    action_names, expression_names, constant_names = _preferred_entries(sections["preferred_names"])
    return LanguagePolicy(
        language_version=language_version,
        operators=operators,
        action_defaults=action_defaults,
        action_preferred_names=action_names,
        expression_preferred_names=expression_names,
        named_constant_preferred_names=constant_names,
        readable_expressions=read_targets(
            readable.get("expressions", []), read_scoped_key, "policy.readable.expressions"
        ),
        expression_defects=read_defects(
            defects.get("expressions", {}), "policy.defects.expressions"
        ),
        expression_event_values=read_event_values(
            event_values.get("expressions", {}), "policy.event_values.expressions"
        ),
        expression_result_roles=tuple(
            (scope, identifier, role)
            for (scope, identifier), role in read_roles(
                result_roles.get("expressions", {}), "policy.result_roles.expressions"
            )
        ),
        source_values=_literals(root.get("literals", {}), metadata),
        member_forms=_members(sections["members"], metadata),
        protected_names=tuple(
            str(item)
            for item in read_array(root.get("protected_names", []), "policy.protected_names")
        ),
        acknowledgeable_codes=tuple(
            read_string(item, f"policy.acknowledgeable[{index}]", nonempty=True)
            for index, item in enumerate(
                read_array(root.get("acknowledgeable", []), "policy.acknowledgeable")
            )
        ),
        parameter_name_entries=read_parameter_names(sections["parameter_names"]),
        parameter_role_entries=read_parameter_roles(sections["parameter_roles"]),
        description_overrides=read_descriptions(sections["descriptions"]),
    )


_SECTIONS: tuple[tuple[str, set[str]], ...] = (
    ("preferred_names", {"actions", "expressions", "named_constants"}),
    ("readable", {"expressions"}),
    ("defects", {"expressions"}),
    ("event_values", {"expressions"}),
    ("result_roles", {"expressions"}),
    ("parameter_names", {"actions", "expressions"}),
    ("parameter_roles", {"actions", "expressions"}),
    ("descriptions", {"expressions"}),
    ("members", {"actions", "expressions"}),
)


def _section(root: Mapping[str, object], name: str, keys: set[str]) -> Mapping[str, object]:
    section = read_table(root.get(name, {}), f"policy.{name}")
    check_keys(section, keys, f"policy.{name}")
    return section


def _preferred_entries(
    preferred: Mapping[str, object],
) -> tuple[
    tuple[tuple[int, str], ...],
    tuple[tuple[ValueType, int, str], ...],
    tuple[tuple[ValueType, int, str], ...],
]:
    return (
        read_preferred_names(
            preferred.get("actions", {}), read_id_key, "policy.preferred_names.actions"
        ),
        tuple(
            (scope, identifier, name)
            for (scope, identifier), name in read_preferred_names(
                preferred.get("expressions", {}),
                read_scoped_key,
                "policy.preferred_names.expressions",
            )
        ),
        tuple(
            (scope, identifier, name)
            for (scope, identifier), name in read_preferred_names(
                preferred.get("named_constants", {}),
                read_scoped_key,
                "policy.preferred_names.named_constants",
            )
        ),
    )


def _operators(value: object, metadata: MetadataSnapshot) -> tuple[OperatorDefinition, ...]:
    result: list[OperatorDefinition] = []
    for token, raw_targets in read_table(value, "policy.operators").items():
        label = f'policy.operators."{token}"'
        syntax = OPERATOR_SYNTAX.get(token)
        if syntax is None:
            raise ValueError(f"{label}: token is not supported by the source grammar")
        precedence, fixity, associativity, short_circuit = syntax
        targets = read_array(raw_targets, label)
        if not targets:
            raise ValueError(f"{label}: list at least one native expression")
        for index, raw_target in enumerate(targets):
            target_label = f"{label}[{index}]"
            scope, identifier = read_scoped_key(raw_target, target_label)
            entry = metadata.expression(scope, identifier)
            if entry is None:
                raise ValueError(f"{target_label}: unknown expression {raw_target}")
            try:
                result.append(
                    OperatorDefinition(
                        token,
                        identifier,
                        scope,
                        tuple(entry.parameter_types),
                        precedence,
                        associativity,
                        fixity,
                        short_circuit,
                        entry.name,
                    )
                )
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"{target_label} ({raw_target}): {exc}") from exc
    return tuple(result)


def _action_defaults(value: object) -> tuple[ActionDefault, ...]:
    result: list[ActionDefault] = []
    for raw_action, raw_parameters in read_table(value, "policy.action_defaults").items():
        label = f"policy.action_defaults.{raw_action}"
        action_id = read_id_key(raw_action, label)
        for raw_parameter, raw_value in read_table(raw_parameters, label).items():
            parameter_label = f"{label}.{raw_parameter}"
            parameter = read_decimal(raw_parameter, parameter_label)
            result.append(
                ActionDefault(action_id, parameter, read_scalar(raw_value, parameter_label))
            )
    return tuple(result)


def _literals(value: object, metadata: MetadataSnapshot) -> tuple[SourceValue, ...]:
    result: list[SourceValue] = []
    for name, raw_value in read_table(value, "policy.literals").items():
        label = f'policy.literals."{name}"'
        if not is_qualified_source_name(name) or not is_source_name(name):
            raise ValueError(f"{label}: name must be a qualified non-keyword source name")
        raw = read_table(raw_value, label)
        check_keys(raw, {"row", "value", "category"}, label, required={"row", "value"})
        row_name = read_string(raw["row"], f"{label}.row", nonempty=True)
        category = (
            None
            if "category" not in raw
            else read_string(raw["category"], f"{label}.category", nonempty=True)
        )
        literal = read_scalar(raw["value"], f"{label}.value")
        scope = literal.type
        rows = tuple(item for item in metadata.named_constants if item.value_type == scope)
        matches = [
            (ordinal, row)
            for ordinal, row in enumerate(rows, start=1)
            if row.name == row_name and (category is None or row.category == category)
        ]
        type_name = ValueType(scope).name.lower()
        if not matches:
            qualifier = "" if category is None else f" in category {category!r}"
            raise ValueError(
                f"{label}: no {type_name} named-constant row is named {row_name!r}{qualifier}"
            )
        if len(matches) > 1:
            categories = ", ".join(sorted({str(row.category) for _, row in matches}))
            raise ValueError(
                f"{label}: {row_name!r} matches {len(matches)} {type_name} rows "
                f'(categories: {categories}); add category = "..."'
            )
        ordinal = matches[0][0]
        result.append(SourceValue(name, RowIdentity("named_constant", ordinal, scope), literal))
    return tuple(result)


# "Name" or "Name(argument: role, ...)"; the receiver is always a card.
_MEMBER_SIGNATURE = re.compile(r"\s*(\w+)\s*(?:\(([^()]*)\))?\s*")
_MEMBER_ARGUMENT = re.compile(r"\s*(\w+)\s*:\s*(\w+)\s*")
_MEMBER_RECEIVER_ROLE = "card"


def _members(value: Mapping[str, object], metadata: MetadataSnapshot) -> tuple[MemberForm, ...]:
    result: list[MemberForm] = []
    for section, kind in (("actions", "action"), ("expressions", "expression")):
        section_label = f"policy.members.{section}"
        for raw_key, raw_signature in read_table(value.get(section, {}), section_label).items():
            label = f"{section_label}.{raw_key}"
            target = read_keyed_target(cast(NativeKind, kind), raw_key, label)
            signature = read_string(raw_signature, label, nonempty=True)
            name, arguments = _member_signature(signature, label)
            label = f"{label} ({name})"
            entry: ActionMetadata | ExpressionMetadata | None
            if target.kind == "action":
                entry = metadata.action(target.identifier)
            else:
                assert target.scope is not None
                entry = metadata.expression(target.scope, target.identifier)
            described = describe(target)
            if entry is None:
                raise ValueError(f"{label}: unknown {described}")
            result_type = entry.return_type if isinstance(entry, ExpressionMetadata) else None
            parameters = tuple(entry.parameter_types)
            if len(arguments) + 1 != len(parameters):
                raise ValueError(
                    f"{label}: {described} takes {len(parameters)} parameter(s) "
                    f"({_type_list(parameters)}); the receiver fills slot 0, so "
                    f"{max(len(parameters) - 1, 0)} argument(s) are required, got {len(arguments)}"
                )
            try:
                result.append(
                    MemberForm(
                        name, target, parameters, result_type, 0, _MEMBER_RECEIVER_ROLE, arguments
                    )
                )
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"{label}: {exc}") from exc
    return tuple(result)


def _member_signature(text: str, label: str) -> tuple[str, tuple[MemberArgument, ...]]:
    match = _MEMBER_SIGNATURE.fullmatch(text)
    if match is None:
        raise ValueError(f'{label}: write "Name" or "Name(argument: role, ...)", got {text!r}')
    name, raw_arguments = match.groups()
    if not is_source_name(name, allow_qualified=False):
        raise ValueError(f"{label}: {name!r} must be an unqualified non-keyword source name")
    arguments: list[MemberArgument] = []
    if raw_arguments is not None and raw_arguments.strip():
        for index, raw_argument in enumerate(raw_arguments.split(","), start=1):
            argument = _MEMBER_ARGUMENT.fullmatch(raw_argument)
            if argument is None:
                raise ValueError(
                    f"{label}: argument {index} must be 'name: role', got {raw_argument.strip()!r}"
                )
            try:
                arguments.append(MemberArgument(index, argument[1], argument[2]))
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"{label}: argument {index}: {exc}") from exc
    return name, tuple(arguments)


def _type_list(types: tuple[int, ...]) -> str:
    return ", ".join(ValueType(item).name.lower() for item in types) or "no parameters"
