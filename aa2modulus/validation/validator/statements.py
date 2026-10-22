"""Event, action and GUI-tree checks."""

from __future__ import annotations

from ...model.control_flow import ACTION_FORLOOP, ACTION_SETVAR
from ...model.display import type_name
from ...model.records import ActionCall, Event, Expression, GuiAction
from ...model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, TypeId, ValueType
from .expressions import validate_expression
from .scope import VariableBinding
from .state import ValidatorState
from .value_types import check_expected_type


def validate_event(
    state: ValidatorState,
    event: Event,
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
) -> None:
    metadata = state.metadata.event(event.id)
    if metadata is None:
        state.reporter.add(
            event, path, "UNKNOWN_EVENT", f"unknown event id {event.id}", field_path=("id",)
        )
        for index, expression in enumerate(event.parameters):
            validate_expression(state, expression, trigger_path, (*path, "parameters", index))
        return
    expected = metadata.parameter_types
    label = state.labels.event(event.id)
    native_note = state.labels.native_note("event", event.id)
    if len(event.parameters) != len(expected):
        state.reporter.add(
            event,
            path,
            "EVENT_ARITY",
            f"{label} expects {len(expected)} parameters, but found {len(event.parameters)}",
            field_path=("parameters",),
            notes=native_note,
        )
    for index, expression in enumerate(event.parameters):
        if index < len(expected):
            check_expected_type(
                state,
                expression,
                expected[index],
                (*path, "parameters", index),
                label,
                index,
                "EVENT_PARAMETER_TYPE",
                native_note,
            )
        validate_expression(state, expression, trigger_path, (*path, "parameters", index))


def validate_action(
    state: ValidatorState,
    action: ActionCall,
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
) -> None:
    metadata = state.metadata.action(action.id)
    if metadata is None:
        state.reporter.add(
            action, path, "UNKNOWN_ACTION", f"unknown action id {action.id}", field_path=("id",)
        )
        for index, expression in enumerate(action.parameters):
            validate_expression(
                state,
                expression,
                trigger_path,
                (*path, "parameters", index),
                allow_assignment_target=action.id in {ACTION_SETVAR, ACTION_FORLOOP} and index == 0,
            )
        return

    expected = metadata.parameter_types
    if len(action.parameters) != len(expected):
        state.reporter.add(
            action,
            path,
            "ACTION_ARITY",
            f"{state.labels.action(action.id)} expects {len(expected)} parameters, "
            f"but found {len(action.parameters)}",
            field_path=("parameters",),
            notes=state.labels.native_note("action", action.id),
        )
    if action.id == ACTION_SETVAR and len(action.parameters) >= 1:
        _validate_assignment(state, action, trigger_path, path)
        return
    if action.id == ACTION_FORLOOP and action.parameters:
        _validate_for_loop(state, action, trigger_path, path)
        _validate_arguments(state, action, expected, trigger_path, path, start=1)
        return
    _validate_arguments(state, action, expected, trigger_path, path, start=0)


def validate_gui_action(
    state: ValidatorState,
    action: GuiAction,
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
) -> None:
    validate_action(state, action.action, trigger_path, (*path, "action"))
    for index, child in enumerate(action.children):
        validate_gui_action(state, child, trigger_path, (*path, "children", index))


def _assignment_binding(
    state: ValidatorState,
    expression: Expression,
    path: tuple[str | int, ...],
) -> VariableBinding | None:
    if expression.id != EXPR_VAR:
        state.reporter.add(
            expression,
            path,
            "INVALID_ASSIGNMENT_TARGET",
            "assignment target must be a variable, but found "
            + (
                "a literal"
                if expression.id == EXPR_CONSTANT
                else "a named constant"
                if expression.id == EXPR_NAMEDCONSTANT
                else state.labels.expression(expression)
            ),
        )
        return None
    binding = state.scope.lookup(expression.variable_name or "")
    if binding is None and not state.native:
        help, fixes = state.undeclared_help(expression.variable_name or "", expression.return_type)
        state.reporter.add(
            expression,
            path,
            "UNDEFINED_VARIABLE",
            f"undefined assignment target {expression.variable_name!r}",
            field_path=("variable_name",),
            help=help,
            fixes=fixes,
        )
    return binding


def _validate_assignment(
    state: ValidatorState,
    action: ActionCall,
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
) -> None:
    target = action.parameters[0]
    binding = _assignment_binding(state, target, (*path, "parameters", 0))
    validate_expression(
        state, target, trigger_path, (*path, "parameters", 0), allow_assignment_target=True
    )
    if len(action.parameters) >= 2:
        value = action.parameters[1]
        expected_type = (
            state.expression_type(target)
            if state.native
            else None
            if binding is None
            else binding.type
        )
        if expected_type is not None and state.expression_type(value) != expected_type:
            state.reporter.add(
                value,
                (*path, "parameters", 1),
                "ASSIGNMENT_TYPE_MISMATCH",
                f"assignment target {target.variable_name!r} expects type "
                f"{type_name(expected_type)}, found "
                f"{type_name(state.expression_type(value))}",
            )
        validate_expression(state, value, trigger_path, (*path, "parameters", 1))
        if state.native and binding is not None and value.return_type != binding.type:
            state.reporter.add(
                value,
                (*path, "parameters", 1),
                "ASSIGNMENT_DECLARATION_TYPE",
                f"variable {binding.name!r} is declared {type_name(binding.type)}, but this "
                f"assignment stores {type_name(value.return_type)}; native "
                "initialization does not check this difference",
                severity="warning",
            )
    for index, expression in enumerate(action.parameters[2:], start=2):
        validate_expression(state, expression, trigger_path, (*path, "parameters", index))


def _validate_for_loop(
    state: ValidatorState,
    action: ActionCall,
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
) -> None:
    """The loop target; the remaining arguments are checked like any action's."""

    target = action.parameters[0]
    binding = _assignment_binding(state, target, (*path, "parameters", 0))
    validate_expression(
        state, target, trigger_path, (*path, "parameters", 0), allow_assignment_target=True
    )
    if binding is not None and binding.type != ValueType.INT:
        state.reporter.add(
            target,
            (*path, "parameters", 0),
            "FOR_LOOP_TARGET_TYPE",
            f"`for` loop target {binding.name!r} must have type int, "
            f"but has type {type_name(binding.type)}",
        )


def _validate_arguments(
    state: ValidatorState,
    action: ActionCall,
    expected: tuple[TypeId, ...],
    trigger_path: tuple[str | int, ...],
    path: tuple[str | int, ...],
    *,
    start: int,
) -> None:
    label = state.labels.action(action.id)
    native_note = state.labels.native_note("action", action.id)
    for index, expression in enumerate(action.parameters[start:], start=start):
        if index < len(expected):
            check_expected_type(
                state,
                expression,
                expected[index],
                (*path, "parameters", index),
                label,
                index,
                "ACTION_PARAMETER_TYPE",
                native_note,
            )
        validate_expression(state, expression, trigger_path, (*path, "parameters", index))
