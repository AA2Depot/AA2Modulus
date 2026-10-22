"""Source literal values against the native constant rows they mirror."""

from __future__ import annotations

from ...metadata.snapshot import MetadataSnapshot
from ...model.types import EXPR_PAYLOAD_MARKERS, ValueType
from ..policy import LanguagePolicy


def validate_literals(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    errors: list[str] = []
    seen_values: set[str] = set()
    for value in policy.source_values:
        label = f'policy.literals."{value.name}"'
        if value.name.casefold() in seen_values:
            errors.append(f"{label}: duplicate source value name")
        seen_values.add(value.name.casefold())
        rows = tuple(
            item for item in metadata.named_constants if item.value_type == value.row.scope
        )
        if (
            value.row.kind != "named_constant"
            or isinstance(value.row.scope, bool)
            or value.row.scope not in range(1, 5)
            or isinstance(value.row.ordinal, bool)
            or not isinstance(value.row.ordinal, int)
            or not 1 <= value.row.ordinal <= len(rows)
        ):
            errors.append(f"{label}: unknown scoped native constant row")
            continue
        row = rows[value.row.ordinal - 1]
        type_name = ValueType(row.value_type).name.lower()
        if row.resolved_value is None:
            errors.append(f"{label}: native row {row.name!r} has no verified value")
        elif value.value != row.resolved_value:
            errors.append(
                f"{label}: value {value.value.value!r} disagrees with native row {row.name!r} "
                f"({type_name} ordinal {value.row.ordinal}), which resolves to "
                f"{row.resolved_value.value!r}"
            )
        winner = metadata.named_constant(row.value_type, row.id)
        if (
            winner is not None
            and winner.resolved_value is not None
            and winner.resolved_value == row.resolved_value
        ):
            errors.append(
                f"{label}: native row {row.name!r} is selected by its own ID "
                f"{type_name}:{row.id}; use the native constant instead of a literal"
            )
        native_getters = tuple(
            entry
            for entry in policy.expression_candidates(metadata, value.name)
            if not entry.parameter_types and entry.id not in EXPR_PAYLOAD_MARKERS
        )
        native_constants = policy.named_constant_candidates(metadata, value.name)
        if native_getters or native_constants:
            errors.append(
                f"{label}: literal name collides with native getter or named-constant candidates"
            )
    return errors
