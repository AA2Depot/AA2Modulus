"""Result roles, parameter names and roles, and description overrides."""

from __future__ import annotations

from ...core.source_names import is_source_name
from ...metadata.identities import WireIdentity
from ...metadata.snapshot import MetadataSnapshot
from ...model.native import ActionMetadata, ExpressionMetadata, NamedConstantMetadata
from ...model.types import EXPR_PAYLOAD_MARKERS, ValueType
from ..policy import LanguagePolicy
from .identities import describe, native_entry, valid_key


def validate_result_roles(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    """A result role reuses a member receiver or argument role of the same type."""

    roles = {(form.receiver_role, form.receiver_type) for form in policy.member_forms} | {
        (item.role, kind)
        for form in policy.member_forms
        for item, kind in zip(form.arguments, form.argument_types, strict=True)
    }
    errors: list[str] = []
    seen: set[tuple[int, int]] = set()
    for scope, identifier, role in policy.expression_result_roles:
        key = WireIdentity("expression", identifier, scope)
        label = f"policy.result_roles.expressions.{describe(key).split(' ', 1)[1]}"
        if (scope, identifier) in seen:
            errors.append(f"{label}: listed more than once")
        seen.add((scope, identifier))
        entry = native_entry(metadata, key) if valid_key(key) else None
        if not isinstance(entry, ExpressionMetadata):
            errors.append(f"{label}: unknown {describe(key)}")
            continue
        if entry.id in EXPR_PAYLOAD_MARKERS:
            errors.append(f"{label}: serialized payload markers have no result role")
            continue
        if (role, entry.return_type) not in roles:
            type_text = ValueType(entry.return_type).name.lower()
            errors.append(
                f"{label}: role {role!r} is not a member receiver or argument role "
                f"of type {type_text}"
            )
    return errors


def validate_parameter_names(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    """Names cover every native slot of a non-member target, distinct and source-shaped."""

    errors: list[str] = []
    seen: set[WireIdentity] = set()
    for key, names in policy.parameter_name_entries:
        section = "actions" if key.kind == "action" else "expressions"
        spelled = describe(key).split(" ", 1)[1]
        label = f"policy.parameter_names.{section}.{spelled}"
        if key in seen:
            errors.append(f"{label}: listed more than once")
        seen.add(key)
        entry = native_entry(metadata, key) if valid_key(key) else None
        if not isinstance(entry, (ActionMetadata, ExpressionMetadata)):
            errors.append(f"{label}: unknown {describe(key)}")
            continue
        if isinstance(entry, ExpressionMetadata) and entry.id in EXPR_PAYLOAD_MARKERS:
            errors.append(f"{label}: serialized payload markers have no parameters")
            continue
        form = policy.member_form_for_target(key)
        if form is not None:
            errors.append(
                f"{label}: {describe(key)} is written as the member '{form.name}'; "
                "name its arguments in [members]"
            )
            continue
        if len(names) != len(entry.parameter_types):
            types = ", ".join(ValueType(item).name.lower() for item in entry.parameter_types)
            errors.append(
                f"{label}: {describe(key)} takes {len(entry.parameter_types)} parameter(s) "
                f"({types or 'none'}), got {len(names)} name(s)"
            )
        for index, name in enumerate(names):
            if not is_source_name(name, allow_qualified=False):
                errors.append(f"{label}[{index}]: {name!r} is not an unqualified non-keyword name")
        folded = [name.casefold() for name in names]
        if len(set(folded)) != len(folded):
            errors.append(f"{label}: parameter names must be distinct")
    return errors


def validate_parameter_roles(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    """A parameter role names a [parameter_names] slot and reuses a member role of its type."""

    roles = {(form.receiver_role, form.receiver_type) for form in policy.member_forms} | {
        (item.role, kind)
        for form in policy.member_forms
        for item, kind in zip(form.arguments, form.argument_types, strict=True)
    }
    errors: list[str] = []
    seen: set[WireIdentity] = set()
    for key, entries in policy.parameter_role_entries:
        section = "actions" if key.kind == "action" else "expressions"
        label = f"policy.parameter_roles.{section}.{describe(key).split(' ', 1)[1]}"
        if key in seen:
            errors.append(f"{label}: listed more than once")
        seen.add(key)
        entry = native_entry(metadata, key) if valid_key(key) else None
        if not isinstance(entry, (ActionMetadata, ExpressionMetadata)):
            errors.append(f"{label}: unknown {describe(key)}")
            continue
        names = policy.parameter_names(key)
        if names is None:
            errors.append(f"{label}: {describe(key)} has no [parameter_names] entry")
            continue
        if len(names) != len(entry.parameter_types):
            # The parameter-name validator reports this invalid slot vector.
            continue
        for name, role in entries:
            if name not in names:
                errors.append(f"{label}.{name}: not a parameter name of {describe(key)}")
                continue
            kind = entry.parameter_types[names.index(name)]
            if (role, kind) not in roles:
                type_text = ValueType(kind).name.lower()
                errors.append(
                    f"{label}.{name}: role {role!r} is not a member receiver or argument role "
                    f"of type {type_text}"
                )
    return errors


def validate_descriptions(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    errors: list[str] = []
    seen: set[WireIdentity] = set()
    for key, _text in policy.description_overrides:
        spelled = describe(key).split(" ", 1)[1]
        label = f"policy.descriptions.{key.kind}s.{spelled}"
        if key in seen:
            errors.append(f"{label}: listed more than once")
        seen.add(key)
        entry = native_entry(metadata, key) if valid_key(key) else None
        if entry is None:
            errors.append(f"{label}: unknown {describe(key)}")
        elif isinstance(entry, NamedConstantMetadata) and entry.id != key.identifier:
            errors.append(
                f"{label}: target uses positional fallback; "
                "source policy requires an explicit named-constant ID"
            )
    return errors
