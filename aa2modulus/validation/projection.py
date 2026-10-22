"""Project serialized GUI actions into AAUnlimited-style executable actions."""

from __future__ import annotations

from dataclasses import dataclass

from ..model.control_flow import (
    ACTION_CONDBREAK,
    ACTION_CONDCONTINUE,
    ACTION_CONDJUMP,
    ACTION_ELSE,
    ACTION_ELSEIF,
    ACTION_FORLOOP,
    ACTION_IF,
    ACTION_LOOP,
    ACTION_SETVAR,
)
from ..model.records import ActionCall, Expression, GuiAction
from ..model.types import EXPR_CONSTANT, ValueType
from ..model.values import Value

EXPR_INT_PLUS = 5
EXPR_BOOL_GTE_INT = 7
EXPR_BOOL_NOT = 11
Path = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class ProjectedAction:
    """An executable action and the GUI-tree path that generated it."""

    action: ActionCall
    path: Path


@dataclass(frozen=True, slots=True)
class DiscardedControl:
    """A BREAK/CONTINUE node ignored by native projection outside a loop."""

    node: GuiAction
    path: Path


class ProjectionError(ValueError):
    """A malformed GUI node that cannot safely be projected."""

    def __init__(self, node: GuiAction, path: Path, message: str) -> None:
        self.node = node
        self.path = path
        self.message = message
        super().__init__(f"{message} at GUI action path {path}")


@dataclass(slots=True)
class _State:
    actions: list[ProjectedAction]
    discarded: list[DiscardedControl]
    if_start: int = -1
    if_end: int = -1
    elseif_ends: list[int] | None = None
    breaks: list[int] | None = None
    continues: list[int] | None = None

    def reset_if(self) -> None:
        self.if_start = -1
        self.if_end = -1
        self.elseif_ends = None

    def child(self) -> _State:
        """Copy branch state while sharing actions and enclosing loop patches."""

        return _State(
            self.actions,
            self.discarded,
            self.if_start,
            self.if_end,
            None if self.elseif_ends is None else list(self.elseif_ends),
            self.breaks,
            self.continues,
        )


def _constant_int(value: int, node: GuiAction) -> Expression:
    return Expression(
        ValueType.INT,
        EXPR_CONSTANT,
        constant=Value.integer(value),
        source_span=node.action.source_span,
        binary_location=node.action.binary_location,
    )


def _constant_bool(value: bool, node: GuiAction) -> Expression:
    return Expression(
        ValueType.BOOL,
        EXPR_CONSTANT,
        constant=Value.boolean(value),
        source_span=node.action.source_span,
        binary_location=node.action.binary_location,
    )


def _not(parameters: tuple[Expression, ...], node: GuiAction) -> Expression:
    return Expression(
        ValueType.BOOL,
        EXPR_BOOL_NOT,
        parameters=parameters,
        source_span=node.action.source_span,
        binary_location=node.action.binary_location,
    )


def _int_gte(left: Expression, right: Expression, node: GuiAction) -> Expression:
    return Expression(
        ValueType.BOOL,
        EXPR_BOOL_GTE_INT,
        parameters=(left, right),
        source_span=node.action.source_span,
        binary_location=node.action.binary_location,
    )


def _int_add(left: Expression, right: Expression, node: GuiAction) -> Expression:
    return Expression(
        ValueType.INT,
        EXPR_INT_PLUS,
        parameters=(left, right),
        source_span=node.action.source_span,
        binary_location=node.action.binary_location,
    )


def _generated_action(
    identifier: int,
    parameters: tuple[Expression, ...],
    node: GuiAction,
) -> ActionCall:
    return ActionCall(
        identifier,
        parameters,
        source_span=node.action.source_span,
        binary_location=node.action.binary_location,
    )


def _jump(distance: int, condition: Expression, node: GuiAction) -> ActionCall:
    return _generated_action(
        ACTION_CONDJUMP,
        (_constant_int(distance, node), condition),
        node,
    )


def _distance(from_index: int, target_index: int) -> int:
    return target_index - from_index - 1


def _patch_jump(actions: list[ProjectedAction], index: int, target: int) -> None:
    projected = actions[index]
    jump = projected.action
    actions[index] = ProjectedAction(
        ActionCall(
            jump.id,
            (
                Expression(
                    ValueType.INT,
                    EXPR_CONSTANT,
                    constant=Value.integer(_distance(index, target)),
                    source_span=jump.source_span,
                    binary_location=jump.binary_location,
                ),
                jump.parameters[1],
            ),
            source_span=jump.source_span,
            binary_location=jump.binary_location,
        ),
        projected.path,
    )


def _emit(state: _State, action: ActionCall, path: Path) -> int:
    state.actions.append(ProjectedAction(action, path))
    return len(state.actions) - 1


def _flatten_nodes(nodes: tuple[GuiAction, ...], state: _State, prefix: Path) -> None:
    for node_index, node in enumerate(nodes):
        path = (*prefix, node_index)
        action = node.action
        if action.id not in {ACTION_IF, ACTION_ELSEIF, ACTION_ELSE}:
            state.reset_if()
        if action.id in {ACTION_IF, ACTION_ELSEIF}:
            _flatten_conditional(node, state, path)
        elif action.id == ACTION_ELSE:
            _flatten_else(node, state, path)
        elif action.id == ACTION_LOOP:
            _flatten_loop(node, state, path)
        elif action.id == ACTION_FORLOOP:
            _flatten_for_loop(node, state, path)
        elif action.id in {ACTION_CONDCONTINUE, ACTION_CONDBREAK}:
            _flatten_loop_control(node, state, path)
        else:
            _emit(state, action, path)
            _flatten_nodes(node.children, state.child(), (*path, "children"))


def _flatten_conditional(node: GuiAction, state: _State, path: Path) -> None:
    """An if or else-if: a skip jump over its body, then a jump to the chain end."""

    action = node.action
    if action.id == ACTION_IF and state.elseif_ends:
        state.reset_if()
    header = _emit(
        state,
        _jump(0, _not(action.parameters, node), node),
        path,
    )
    _flatten_nodes(node.children, _State(state.actions, state.discarded), (*path, "children"))
    end_jump = _emit(
        state,
        _jump(0, _constant_bool(True, node), node),
        path,
    )
    _patch_jump(state.actions, header, end_jump + 1)
    if action.id == ACTION_IF or state.if_start == -1:
        state.if_start = header
        state.if_end = end_jump
        state.elseif_ends = []
    else:
        _patch_jump(state.actions, state.if_end, end_jump + 1)
        for elseif_end in state.elseif_ends or ():
            _patch_jump(state.actions, elseif_end, end_jump + 1)
        assert state.elseif_ends is not None
        state.elseif_ends.append(end_jump)


def _flatten_else(node: GuiAction, state: _State, path: Path) -> None:
    """An else body; earlier chain ends now jump past it."""

    _flatten_nodes(node.children, _State(state.actions, state.discarded), (*path, "children"))
    if state.if_start != -1:
        end = len(state.actions) - 1
        _patch_jump(state.actions, state.if_end, end + 1)
        for elseif_end in state.elseif_ends or ():
            _patch_jump(state.actions, elseif_end, end + 1)
    state.reset_if()


def _flatten_loop(node: GuiAction, state: _State, path: Path) -> None:
    """A loop body followed by a jump back to its head."""

    loop_state = _State(state.actions, state.discarded, breaks=[], continues=[])
    loop_head = len(state.actions)
    _flatten_nodes(node.children, loop_state, (*path, "children"))
    loop_end = len(state.actions)
    if loop_head != loop_end:
        _emit(
            state,
            _jump(
                _distance(loop_end, loop_head),
                _not((_constant_bool(False, node),), node),
                node,
            ),
            path,
        )
        loop_end = len(state.actions)
        for index in loop_state.continues or ():
            _patch_jump(state.actions, index, loop_head)
        for index in loop_state.breaks or ():
            _patch_jump(state.actions, index, loop_end)


def _flatten_for_loop(node: GuiAction, state: _State, path: Path) -> None:
    """Initialize, test, body, increment and jump back, as AAUnlimited expands it."""

    action = node.action
    if len(action.parameters) < 3:
        raise ProjectionError(
            node,
            path,
            f"for-loop needs at least 3 parameters, got {len(action.parameters)}",
        )
    target, start, limit = action.parameters[:3]
    _emit(state, _generated_action(ACTION_SETVAR, (target, start), node), path)
    loop_head = len(state.actions)
    _emit(
        state,
        _jump(0, _int_gte(target, limit, node), node),
        path,
    )
    loop_state = _State(state.actions, state.discarded, breaks=[], continues=[])
    _flatten_nodes(node.children, loop_state, (*path, "children"))
    continue_point = len(state.actions)
    _emit(
        state,
        _generated_action(
            ACTION_SETVAR,
            (target, _int_add(target, _constant_int(1, node), node)),
            node,
        ),
        path,
    )
    end_jump = len(state.actions)
    _emit(state, _jump(_distance(end_jump, loop_head), _constant_bool(True, node), node), path)
    loop_end = len(state.actions)
    _patch_jump(state.actions, loop_head, loop_end)
    for index in loop_state.continues or ():
        _patch_jump(state.actions, index, continue_point)
    for index in loop_state.breaks or ():
        _patch_jump(state.actions, index, loop_end)


def _flatten_loop_control(node: GuiAction, state: _State, path: Path) -> None:
    """A conditional break or continue, discarded outside a loop."""

    action = node.action
    patches = state.continues if action.id == ACTION_CONDCONTINUE else state.breaks
    if patches is None:
        state.discarded.append(DiscardedControl(node, path))
    else:
        if len(action.parameters) < 1:
            kind = "continue" if action.id == ACTION_CONDCONTINUE else "break"
            raise ProjectionError(
                node,
                path,
                f"conditional {kind} needs at least 1 condition, got {len(action.parameters)}",
            )
        index = _emit(state, _jump(0, action.parameters[0], node), path)
        patches.append(index)


def project_gui_actions(
    gui_actions: tuple[GuiAction, ...],
) -> tuple[tuple[ProjectedAction, ...], tuple[DiscardedControl, ...]]:
    """Project GUI actions while retaining origins and discarded controls."""

    actions: list[ProjectedAction] = []
    discarded: list[DiscardedControl] = []
    _flatten_nodes(gui_actions, _State(actions, discarded), ())
    return tuple(actions), tuple(discarded)


def flatten_gui_actions(gui_actions: tuple[GuiAction, ...]) -> tuple[ActionCall, ...]:
    """Return the native-style executable action projection of a GUI tree."""

    projected, _ = project_gui_actions(gui_actions)
    return tuple(item.action for item in projected)
