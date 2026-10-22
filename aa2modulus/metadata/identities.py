"""Native row and serialized lookup identities shared by facts and source policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ..model.types import TypeId

NativeKind = Literal["action", "event", "expression", "named_constant"]
type NativeMetadata = ActionMetadata | EventMetadata | ExpressionMetadata | NamedConstantMetadata


@dataclass(frozen=True, slots=True)
class WireIdentity:
    kind: NativeKind
    identifier: int
    scope: TypeId | None = None


@dataclass(frozen=True, slots=True)
class RowIdentity:
    kind: NativeKind
    ordinal: int
    scope: TypeId | None = None


def native_key(entry: NativeMetadata) -> WireIdentity:
    if isinstance(entry, ActionMetadata):
        return WireIdentity("action", entry.id)
    if isinstance(entry, EventMetadata):
        return WireIdentity("event", entry.id)
    if isinstance(entry, ExpressionMetadata):
        return WireIdentity("expression", entry.id, entry.return_type)
    return WireIdentity("named_constant", entry.id, entry.value_type)
