"""Receiver member forms."""

from __future__ import annotations

from ...metadata.snapshot import MetadataSnapshot
from ...model.native import ActionMetadata, ExpressionMetadata
from ...model.types import EXPR_PAYLOAD_MARKERS, ValueType
from ..policy import LanguagePolicy
from .identities import describe, native_entry, valid_key


def validate_member_forms(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str, int]] = set()
    for form in policy.member_forms:
        label = f"policy.members: {describe(form.target)} ({form.name})"
        if not valid_key(form.target) or form.target.kind not in ("action", "expression"):
            errors.append(f"{label}: requires a native action or expression target")
            continue
        entry = native_entry(metadata, form.target)
        if not isinstance(entry, (ActionMetadata, ExpressionMetadata)):
            errors.append(f"{label}: unknown {describe(form.target)}")
            continue
        result = entry.return_type if isinstance(entry, ExpressionMetadata) else None
        if form.parameter_types != entry.parameter_types or form.result_type != result:
            errors.append(
                f"{label}: signature differs from native {describe(form.target)}; "
                "member forms preserve native parameter order and result type"
            )
            continue
        if (
            ValueType.INVALID in entry.parameter_types
            or (isinstance(entry, ExpressionMetadata) and entry.id in EXPR_PAYLOAD_MARKERS)
            or not entry.parameter_types
        ):
            errors.append(
                f"{label}: target requires a structured source form, serialized payload or "
                "receiver slot"
            )
            continue
        if entry.parameter_types[0] != ValueType.INT:
            errors.append(
                f"{label}: receiver slot 0 must be a native int "
                f"({describe(form.target)} slot 0 is "
                f"{ValueType(entry.parameter_types[0]).name.lower()})"
            )
        if form.target.kind == "action":
            preferred = policy.preferred_action_name(form.target.identifier)
        else:
            assert form.target.scope is not None
            preferred = policy.preferred_expression_name(form.target.scope, form.target.identifier)
        if preferred is not None:
            errors.append(
                f"{label}: {describe(form.target)} also has preferred name {preferred!r}; "
                "a card-first target is written only as its member form, so remove the preferred "
                "name"
            )
        key = (form.target.kind, form.name.casefold(), len(form.arguments))
        if key in seen:
            errors.append(
                f"{label}: duplicate member form for this spelling, target kind and argument count"
            )
        seen.add(key)
    return errors
