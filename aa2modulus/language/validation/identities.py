"""Native target lookup and the spelling of targets and types in policy errors."""

from __future__ import annotations

from ...metadata.identities import NativeMetadata, WireIdentity
from ...metadata.snapshot import MetadataSnapshot
from ...model.types import TypeId, ValueType


def native_entry(metadata: MetadataSnapshot, key: WireIdentity) -> NativeMetadata | None:
    if key.kind == "action":
        return metadata.action(key.identifier)
    if key.kind == "event":
        return metadata.event(key.identifier)
    if key.scope is None:
        return None
    if key.kind == "expression":
        return metadata.expression(key.scope, key.identifier)
    return metadata.named_constant(key.scope, key.identifier)


def valid_key(key: WireIdentity) -> bool:
    if key.kind not in {"action", "event", "expression", "named_constant"}:
        return False
    if (
        isinstance(key.identifier, bool)
        or not isinstance(key.identifier, int)
        or key.identifier < 1
    ):
        return False
    if key.kind in {"action", "event"}:
        return key.scope is None
    return (
        isinstance(key.scope, int)
        and not isinstance(key.scope, bool)
        and key.scope in (range(1, 5) if key.kind == "named_constant" else range(5))
    )


def native_candidates(
    metadata: MetadataSnapshot, key: WireIdentity, name: str
) -> tuple[NativeMetadata, ...]:
    query = getattr(metadata, key.kind + "_candidates_by_name", None)
    if not callable(query):
        return ()
    entries = query(name, key.scope) if key.kind == "named_constant" else query(name)
    return tuple(entries)


def describe(key: WireIdentity) -> str:
    """Spell a wire identity the way the policy file writes it."""

    if key.scope is None:
        return f"{key.kind} {key.identifier}"
    scope = ValueType(key.scope).name.lower() if key.scope in range(5) else str(key.scope)
    return f"{key.kind} {scope}:{key.identifier}"


def identities_text(keys: set[WireIdentity] | tuple[WireIdentity, ...]) -> str:
    return "[" + ", ".join(sorted(describe(key) for key in keys)) + "]"


def types_text(types: tuple[TypeId, ...]) -> str:
    return ", ".join(
        ValueType(item).name.lower() if item in range(ValueType.N_TYPES) else str(item)
        for item in types
    )


def scoped_text(scope: TypeId, identifier: int) -> str:
    return f"{types_text((scope,))}:{identifier}"


def valid_policy_id(identifier: object) -> bool:
    return isinstance(identifier, int) and not isinstance(identifier, bool) and identifier > 0


def valid_policy_scope(value_type: object) -> bool:
    return (
        isinstance(value_type, int)
        and not isinstance(value_type, bool)
        and 0 <= value_type < int(ValueType.N_TYPES)
    )
