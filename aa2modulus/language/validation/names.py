"""Preferred names, namespace roots and protected names."""

from __future__ import annotations

from ...core.source_names import is_source_name
from ...metadata.identities import WireIdentity, native_key
from ...metadata.snapshot import MetadataSnapshot
from ...model.native import ExpressionMetadata, NamedConstantMetadata
from ...model.types import EXPR_PAYLOAD_MARKERS
from ..policy import LanguagePolicy
from .identities import (
    identities_text,
    native_candidates,
    native_entry,
    valid_key,
    valid_policy_id,
    valid_policy_scope,
)


def validate_preferred_names(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    """Preferred names name known native targets by explicit ID."""

    errors: list[str] = []
    for identifier, _ in policy.action_preferred_names:
        if not valid_policy_id(identifier):
            errors.append(
                f"policy.preferred_names.actions[{identifier!r}]: target ID must be a positive "
                "integer"
            )
            continue
        if metadata.action(identifier) is None:
            errors.append(
                f"policy.preferred_names.actions[{identifier!r}]: preferred name references "
                f"unknown action {identifier}"
            )
    for return_type, identifier, _ in policy.expression_preferred_names:
        if not valid_policy_scope(return_type) or not valid_policy_id(identifier):
            errors.append(
                f"policy.preferred_names.expressions[{return_type}:{identifier}]: target "
                "requires a supported type scope and positive integer ID"
            )
            continue
        if identifier in EXPR_PAYLOAD_MARKERS:
            errors.append(
                f"policy.preferred_names.expressions[{return_type}:{identifier}]: preferred "
                "names cannot target serialized payload markers"
            )
        if metadata.expression(return_type, identifier) is None:
            errors.append(
                f"policy.preferred_names.expressions[{return_type}:{identifier}]: preferred "
                f"name references unknown expression {return_type}:{identifier}"
            )
    for value_type, identifier, _ in policy.named_constant_preferred_names:
        if not valid_policy_scope(value_type) or not valid_policy_id(identifier):
            errors.append(
                f"policy.preferred_names.named_constants[{value_type}:{identifier}]: target "
                "requires a supported type scope and positive integer ID"
            )
            continue
        named_entry = metadata.named_constant(value_type, identifier)
        if named_entry is None:
            errors.append(
                f"policy.preferred_names.named_constants[{value_type}:{identifier}]: preferred "
                f"name references unknown named constant {value_type}:{identifier}"
            )
        elif named_entry.id != identifier:
            errors.append(
                f"policy.preferred_names.named_constants[{value_type}:{identifier}]: target "
                "uses positional fallback; source policy requires an explicit named-constant ID"
            )
    return errors


def configured_names(policy: LanguagePolicy) -> tuple[tuple[WireIdentity, str], ...]:
    """Every preferred name with its target."""

    return (
        tuple(
            (WireIdentity("action", identifier), name)
            for identifier, name in policy.action_preferred_names
        )
        + tuple(
            (WireIdentity("expression", identifier, scope), name)
            for scope, identifier, name in policy.expression_preferred_names
        )
        + tuple(
            (WireIdentity("named_constant", identifier, scope), name)
            for scope, identifier, name in policy.named_constant_preferred_names
        )
    )


def validate_names(
    policy: LanguagePolicy,
    metadata: MetadataSnapshot,
    names: tuple[tuple[WireIdentity, str], ...],
) -> list[str]:
    errors: list[str] = []
    canonical: dict[tuple[object, ...], WireIdentity] = {}
    for key, name in names:
        if not valid_key(key):
            continue  # validate_preferred_names reports malformed targets.
        entry = native_entry(metadata, key)
        if entry is None:
            continue
        original = native_candidates(metadata, key, name)
        original_keys = {native_key(item) for item in original}
        if original_keys and key not in original_keys:
            errors.append(
                f"policy.names ({name}): preferred name would displace native targets "
                f"{identities_text(original_keys)}; choose another name"
            )
        if isinstance(entry, NamedConstantMetadata) and any(
            isinstance(item, NamedConstantMetadata) and item.resolved_value != entry.resolved_value
            for item in original
            if native_key(item) == key
        ):
            errors.append(
                f"policy.names ({name}): preferred name names a shadowed native constant value"
            )
        signature: tuple[object, ...] = (key.kind, name.casefold(), key.scope)
        if isinstance(entry, ExpressionMetadata):
            signature += (entry.parameter_types,)
        previous = canonical.get(signature)
        if previous is not None and previous != key:
            errors.append(f"policy.names ({name}): canonical spelling has multiple exact targets")
        canonical[signature] = key
    return errors


def validate_namespace_roots(
    policy: LanguagePolicy,
    names: tuple[tuple[WireIdentity, str], ...],
) -> list[str]:
    """Roots are case-sensitive: uppercase initial, unique ignoring case."""

    qualified = [(f"policy.names ({name})", name) for _, name in names]
    qualified.extend((f'policy.literals."{item.name}"', item.name) for item in policy.source_values)
    errors: list[str] = []
    by_fold: dict[str, str] = {}
    reported: set[str] = set()
    for label, name in qualified:
        if "." not in name:
            continue
        root = name.split(".", 1)[0]
        if not ("A" <= root[:1] <= "Z") and root not in reported:
            reported.add(root)
            errors.append(
                f"{label}: namespace root {root!r} must start with an uppercase ASCII letter"
            )
        previous = by_fold.setdefault(root.casefold(), root)
        if previous != root and root not in reported:
            reported.add(root)
            errors.append(f"{label}: namespace roots {previous!r} and {root!r} differ only by case")
    return errors


def validate_protected_names(
    policy: LanguagePolicy,
    metadata: MetadataSnapshot,
    names: tuple[tuple[WireIdentity, str], ...],
) -> list[str]:
    """Protected names are unqualified preferred names of one zero-argument expression."""

    errors: list[str] = []
    seen: set[str] = set()
    for index, name in enumerate(policy.protected_names):
        label = f"policy.protected_names[{index}] ({name})"
        folded = name.casefold()
        if folded in seen:
            errors.append(f"{label}: duplicate protected name")
        seen.add(folded)
        if not is_source_name(name, allow_qualified=False):
            errors.append(f"{label}: must be an unqualified source name")
            continue
        targets = {key for key, spelling in names if spelling.casefold() == folded}
        if len(targets) != 1:
            errors.append(f"{label}: must be the preferred name of exactly one target")
            continue
        key = next(iter(targets))
        entry = native_entry(metadata, key) if key.kind == "expression" else None
        if not isinstance(entry, ExpressionMetadata) or entry.parameter_types:
            errors.append(f"{label}: must name a zero-argument expression")
    return errors
