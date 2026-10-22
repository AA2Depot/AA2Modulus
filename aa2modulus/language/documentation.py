"""Documentation keys and text shared by the language server and documentation exports."""

from __future__ import annotations

from collections.abc import Iterable

from ..metadata.identities import NativeMetadata, native_key
from ..model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ..model.types import ValueType
from .policy import LanguagePolicy
from .values import SourceValue

type DocumentedMetadata = NativeMetadata | SourceValue


def builtin_anchor(entry: DocumentedMetadata, *, ordinal: int | None = None) -> str:
    """Identify a native record, retaining duplicate constant positions.

    Constant IDs are not unique; their reference ordinal is one-based within
    the original registry type scope, rather than an explicit numeric ID.
    """

    if isinstance(entry, SourceValue):
        return entry.documentation_key
    if isinstance(entry, ActionMetadata):
        return f"action-{entry.id}"
    if isinstance(entry, EventMetadata):
        return f"event-{entry.id}"
    if isinstance(entry, ExpressionMetadata):
        return f"expression-{ValueType(entry.return_type).name.lower()}-{entry.id}"
    if ordinal is None or ordinal < 1:
        raise ValueError("named-constant documentation requires its positive scoped ordinal")
    return f"named-constant-{ValueType(entry.value_type).name.lower()}-{ordinal}"


def constant_ordinals(
    constants: Iterable[NamedConstantMetadata],
) -> tuple[tuple[NamedConstantMetadata, int], ...]:
    """Each constant with its one-based position within its value type, in registry order."""

    counts: dict[int, int] = {}
    result: list[tuple[NamedConstantMetadata, int]] = []
    for entry in constants:
        counts[entry.value_type] = counts.get(entry.value_type, 0) + 1
        result.append((entry, counts[entry.value_type]))
    return tuple(result)


def builtin_description(policy: LanguagePolicy, entry: DocumentedMetadata) -> str:
    """The policy description override, else the native description."""

    if isinstance(entry, SourceValue):
        return ""
    override = policy.description_override(native_key(entry))
    return override if override is not None else entry.description
