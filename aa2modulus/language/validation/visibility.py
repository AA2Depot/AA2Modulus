"""Readable, defective and event-dependent expressions, and acknowledgeable hazards."""

from __future__ import annotations

from ...core.diagnostics import NATIVE_HAZARD_CODES
from ...metadata.identities import WireIdentity
from ...metadata.snapshot import MetadataSnapshot
from ...model.native import ExpressionMetadata
from ...model.types import EXPR_PAYLOAD_MARKERS, ValueType
from ..policy import LanguagePolicy
from .identities import describe, native_entry, valid_key


def validate_readable(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[int, int]] = set()
    for index, (scope, identifier) in enumerate(policy.readable_expressions):
        key = WireIdentity("expression", identifier, scope)
        label = f"policy.readable.expressions[{index}] ({describe(key).split(' ', 1)[1]})"
        if (scope, identifier) in seen:
            errors.append(f"{label}: listed more than once")
        seen.add((scope, identifier))
        entry = native_entry(metadata, key) if valid_key(key) else None
        if not isinstance(entry, ExpressionMetadata):
            errors.append(f"{label}: unknown {describe(key)}")
            continue
        if entry.id in EXPR_PAYLOAD_MARKERS:
            errors.append(f"{label}: serialized payload markers cannot be readable")
            continue
        if policy.preferred_expression_name(scope, identifier) is None:
            errors.append(
                f"{label}: needs a preferred_names.expressions entry; readable output "
                "uses that policy-chosen name"
            )
        if entry.declared_return_type == entry.return_type:
            errors.append(
                f"{label}: native declaration already returns "
                f"{ValueType(entry.return_type).name.lower()}; remove the readable marker"
            )
    return errors


def validate_defects(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    # `declared` pins the registry signature the defect was reviewed against, so
    # a regenerated registry with a fixed declaration fails here instead of
    # keeping a stale rejection.
    errors: list[str] = []
    for scope, identifier, declared, _reason in policy.expression_defects:
        key = WireIdentity("expression", identifier, scope)
        label = f"policy.defects.expressions ({describe(key).split(' ', 1)[1]})"
        entry = native_entry(metadata, key) if valid_key(key) else None
        if not isinstance(entry, ExpressionMetadata):
            errors.append(f"{label}: unknown {describe(key)}")
            continue
        if entry.id in EXPR_PAYLOAD_MARKERS:
            errors.append(f"{label}: serialized payload markers cannot be defects")
            continue
        native = tuple(int(item) for item in entry.parameter_types)
        if native != tuple(int(item) for item in declared):
            names = ", ".join(ValueType(item).name.lower() for item in native)
            errors.append(
                f"{label}: native declaration is now ({names}); review the defect "
                "against the regenerated registry"
            )
    return errors


def validate_event_values(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    # `callback` pins the native implementation the entry was reviewed against.
    errors: list[str] = []
    for item in policy.expression_event_values:
        label = f"policy.event_values.expressions ({describe(item.target).split(' ', 1)[1]})"
        entry = native_entry(metadata, item.target) if valid_key(item.target) else None
        if not isinstance(entry, ExpressionMetadata):
            errors.append(f"{label}: unknown {describe(item.target)}")
            continue
        if entry.id in EXPR_PAYLOAD_MARKERS:
            errors.append(f"{label}: serialized payload markers have no callback")
            continue
        if entry.implementation != item.callback:
            errors.append(
                f"{label}: native callback is now {entry.implementation}; review the entry "
                "against the regenerated registry"
            )
        listed = [event_id for _, event_ids in item.events for event_id in event_ids]
        for event_id in sorted(set(listed)):
            if metadata.event(event_id) is None:
                errors.append(f"{label}: unknown event {event_id}")
            if listed.count(event_id) > 1:
                errors.append(f"{label}: event {event_id} is listed under more than one type")
    return errors


def validate_acknowledgeable(policy: LanguagePolicy) -> list[str]:
    """Only validator hazard codes, each once, may be acknowledged in source."""

    errors: list[str] = []
    seen: set[str] = set()
    for index, code in enumerate(policy.acknowledgeable_codes):
        label = f"policy.acknowledgeable[{index}] ({code})"
        if code in seen:
            errors.append(f"{label}: duplicate code")
        seen.add(code)
        if code not in NATIVE_HAZARD_CODES:
            errors.append(f"{label}: not a native hazard code the validator reports")
    return errors
