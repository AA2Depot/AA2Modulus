"""Operator and action-default checks."""

from __future__ import annotations

from ...metadata.snapshot import MetadataSnapshot
from ...model.types import TypeId, ValueType
from ..policy import LanguagePolicy
from .identities import scoped_text, types_text


def validate_operators(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    """Operators name native expressions with their exact signature and evaluation."""

    errors: list[str] = []
    seen_operators: set[tuple[str, TypeId, tuple[TypeId, ...]]] = set()
    for operator in policy.operators:
        target = scoped_text(operator.return_type, operator.expression_id)
        label = f'policy.operators."{operator.token}" ({target})'
        operator_key = (operator.token, operator.return_type, operator.parameter_types)
        if operator_key in seen_operators:
            errors.append(f"{label}: duplicate operator signature for this token")
        seen_operators.add(operator_key)
        entry = metadata.expression(operator.return_type, operator.expression_id)
        if entry is None:
            errors.append(f"{label}: unknown expression {target}")
            continue
        if tuple(entry.parameter_types) != operator.parameter_types:
            errors.append(
                f"{label}: native parameters are ({types_text(entry.parameter_types)}), "
                f"operator expects ({types_text(operator.parameter_types)})"
            )
        # Pinned Thread::EvaluateExpression handles these scoped IDs before
        # ordinary eager parameter evaluation. Policy cannot change that.
        native_short_circuit = entry.return_type == ValueType.BOOL and entry.id in {4, 5}
        if operator.short_circuit != native_short_circuit:
            errors.append(f"{label}: short_circuit disagrees with the native evaluation")
    return errors


def validate_action_defaults(policy: LanguagePolicy, metadata: MetadataSnapshot) -> list[str]:
    """Action defaults match native parameter types and form a trailing suffix."""

    errors: list[str] = []
    seen_defaults: set[tuple[int, int]] = set()
    defaults_by_action: dict[int, set[int]] = {}
    for default in policy.action_defaults:
        label = f"policy.action_defaults.{default.action_id}.{default.parameter_index}"
        default_key = (default.action_id, default.parameter_index)
        if default_key in seen_defaults:
            errors.append(f"{label}: duplicate action default")
        seen_defaults.add(default_key)
        action = metadata.action(default.action_id)
        if action is None:
            errors.append(f"{label}: unknown action {default.action_id}")
            continue
        if default.parameter_index >= len(action.parameter_types):
            errors.append(
                f"{label}: parameter {default.parameter_index} is outside action "
                f"{default.action_id} ({types_text(action.parameter_types)})"
            )
        elif action.parameter_types[default.parameter_index] != default.value.type:
            errors.append(
                f"{label}: value type {types_text((default.value.type,))} does not match "
                f"parameter type {types_text((action.parameter_types[default.parameter_index],))}"
            )
        else:
            defaults_by_action.setdefault(default.action_id, set()).add(default.parameter_index)
    for action_id, indexes in defaults_by_action.items():
        action = metadata.action(action_id)
        assert action is not None
        expected = set(range(min(indexes), len(action.parameter_types)))
        if indexes != expected:
            errors.append(
                f"policy.action_defaults.{action_id}: defaults must form a trailing parameter "
                "suffix"
            )
    return errors
