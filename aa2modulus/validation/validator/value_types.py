"""Type checks on values, declarations and positional parameters."""

from __future__ import annotations

from ...model.display import type_name
from ...model.records import Expression, GlobalVariable, Variable
from ...model.types import TypeId, ValueType
from ...model.values import Value
from .state import ValidatorState


def known_type(value: TypeId, *, allow_invalid: bool = True) -> bool:
    try:
        value_type = ValueType(value)
    except ValueError:
        return False
    if value_type is ValueType.N_TYPES:
        return False
    return allow_invalid or value_type is not ValueType.INVALID


def check_declared_type(
    state: ValidatorState,
    node: GlobalVariable | Variable,
    path: tuple[str | int, ...],
    label: str,
) -> None:
    if not known_type(node.type, allow_invalid=False):
        state.reporter.add(
            node,
            path,
            "INVALID_VARIABLE_TYPE",
            f"{label} {node.name!r} has invalid type {type_name(node.type)}",
            field_path=("type",),
        )


def check_expected_type(
    state: ValidatorState,
    actual: Expression,
    expected: TypeId,
    path: tuple[str | int, ...],
    label: str,
    index: int,
    code: str,
    notes: tuple[str, ...] = (),
) -> None:
    if expected is ValueType.INVALID and not state.native:
        return
    actual_type = state.expression_type(actual)
    if actual_type != expected:
        state.reporter.add(
            actual,
            path,
            code,
            f"parameter {index + 1} of {label} expects {type_name(expected)}, "
            f"found {type_name(actual_type)}",
            field_path=("return_type",),
            notes=notes,
        )


def validate_value(
    state: ValidatorState,
    value: Value,
    path: tuple[str | int, ...],
    expected: TypeId | None = None,
) -> None:
    if not known_type(value.type):
        state.reporter.add(
            value,
            path,
            "INVALID_VALUE_TYPE",
            f"value has an invalid type ({type_name(value.type)})",
        )
    if expected is not None and value.type != expected:
        state.reporter.add(
            value,
            path,
            "CONSTANT_TYPE_MISMATCH",
            f"constant is {type_name(value.type)}, but the expression expects "
            f"{type_name(expected)}",
            severity=state.authoring_severity,
        )
