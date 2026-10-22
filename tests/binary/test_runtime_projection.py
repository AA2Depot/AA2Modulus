"""GUI flattening patches branch jumps and loop controls as AAUnlimited does."""

from __future__ import annotations

from aa2modulus.model.records import ActionCall, Expression, GuiAction
from aa2modulus.model.types import EXPR_CONSTANT, ValueType
from aa2modulus.model.values import Value
from aa2modulus.validation.projection import flatten_gui_actions


def condition(value: bool = True) -> Expression:
    return Expression(ValueType.BOOL, EXPR_CONSTANT, constant=Value.boolean(value))


def integer(value: int) -> Expression:
    return Expression(ValueType.INT, EXPR_CONSTANT, constant=Value.integer(value))


def variable(name: str = "counter") -> Expression:
    return Expression(ValueType.INT, 2, variable_name=name)


def ids(actions):
    return [action.id for action in actions]


def jump_target(action, index: int) -> int:
    return index + 1 + action.parameters[0].constant.value


def test_if_elseif_else_flattening_patches_all_end_jumps():
    actions = flatten_gui_actions(
        (
            GuiAction(ActionCall(2, (condition(),)), (GuiAction(ActionCall(108)),)),
            GuiAction(ActionCall(3, (condition(False),)), (GuiAction(ActionCall(108)),)),
            GuiAction(ActionCall(4), (GuiAction(ActionCall(108)),)),
        )
    )

    assert ids(actions) == [5, 108, 5, 5, 108, 5, 108]
    assert jump_target(actions[0], 0) == 3
    assert jump_target(actions[2], 2) == 7
    assert jump_target(actions[3], 3) == 6
    assert jump_target(actions[5], 5) == 7


def test_loop_break_and_continue_target_loop_boundaries():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(6),
                (
                    GuiAction(ActionCall(7, (condition(),))),
                    GuiAction(ActionCall(8, (condition(),))),
                    GuiAction(ActionCall(108)),
                ),
            ),
        )
    )

    assert ids(actions) == [5, 5, 108, 5]
    assert jump_target(actions[0], 0) == 4
    assert jump_target(actions[1], 1) == 0
    assert jump_target(actions[3], 3) == 0


def test_for_loop_emits_initialization_header_increment_and_back_jump():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(9, (variable(), integer(0), integer(3))),
                (GuiAction(ActionCall(108)),),
            ),
        )
    )

    assert ids(actions) == [1, 5, 108, 1, 5]
    assert actions[0].parameters[0].variable_name == "counter"
    assert jump_target(actions[1], 1) == 5
    assert jump_target(actions[4], 4) == 1


def test_if_child_discards_the_enclosing_loop_context():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(6),
                (
                    GuiAction(
                        ActionCall(2, (condition(),)),
                        (
                            GuiAction(ActionCall(7, (condition(),))),
                            GuiAction(ActionCall(8, (condition(),))),
                        ),
                    ),
                ),
            ),
        )
    )

    # Native IF child traversal starts a fresh state, so these controls are
    # discarded. The IF's two jumps remain inside the outer loop.
    assert ids(actions) == [5, 5, 5]
    assert [jump_target(action, i) for i, action in enumerate(actions)] == [2, 2, 0]


def test_nested_loops_patch_controls_to_the_innermost_loop():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(6),
                (
                    GuiAction(
                        ActionCall(6),
                        (
                            GuiAction(ActionCall(7, (condition(),))),
                            GuiAction(ActionCall(8, (condition(),))),
                        ),
                    ),
                    GuiAction(ActionCall(7, (condition(),))),
                    GuiAction(ActionCall(8, (condition(),))),
                ),
            ),
        )
    )

    assert ids(actions) == [5, 5, 5, 5, 5, 5]
    assert [jump_target(action, i) for i, action in enumerate(actions)] == [
        3,
        0,
        0,
        6,
        0,
        0,
    ]


def test_ordinary_action_children_keep_enclosing_loop_patch_lists():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(6),
                (
                    GuiAction(
                        ActionCall(108),
                        (
                            GuiAction(ActionCall(7, (condition(),))),
                            GuiAction(ActionCall(8, (condition(),))),
                        ),
                    ),
                ),
            ),
        )
    )

    assert ids(actions) == [108, 5, 5, 5]
    assert jump_target(actions[1], 1) == 4
    assert jump_target(actions[2], 2) == 0
    assert jump_target(actions[3], 3) == 0


def test_for_loop_controls_use_native_continue_point():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(9, (variable(), integer(0), integer(3))),
                (
                    GuiAction(ActionCall(7, (condition(),))),
                    GuiAction(ActionCall(8, (condition(),))),
                ),
            ),
        )
    )

    assert ids(actions) == [1, 5, 5, 5, 1, 5]
    assert [jump_target(action, i) for i, action in enumerate(actions) if action.id == 5] == [
        6,
        6,
        4,
        1,
    ]


def test_projection_ignores_extra_for_and_conditional_control_parameters():
    extra = integer(99)
    controls = (
        GuiAction(ActionCall(7, (condition(), extra))),
        GuiAction(ActionCall(8, (condition(False), extra))),
    )
    with_extras = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(9, (variable(), integer(0), integer(3), extra)),
                controls,
            ),
        )
    )
    without_extras = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(9, (variable(), integer(0), integer(3))),
                (
                    GuiAction(ActionCall(7, (condition(),))),
                    GuiAction(ActionCall(8, (condition(False),))),
                ),
            ),
        )
    )

    assert with_extras == without_extras


def test_controls_outside_loops_and_their_children_are_discarded():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(7, (condition(),)),
                (GuiAction(ActionCall(108)),),
            ),
            GuiAction(
                ActionCall(8, (condition(),)),
                (GuiAction(ActionCall(109)),),
            ),
        )
    )

    assert actions == ()


def test_if_elseif_else_each_discard_loop_controls_with_native_jumps():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(6),
                (
                    GuiAction(
                        ActionCall(2, (condition(),)), (GuiAction(ActionCall(7, (condition(),))),)
                    ),
                    GuiAction(
                        ActionCall(3, (condition(),)), (GuiAction(ActionCall(8, (condition(),))),)
                    ),
                    GuiAction(ActionCall(4), (GuiAction(ActionCall(7, (condition(),))),)),
                ),
            ),
        )
    )

    assert ids(actions) == [5, 5, 5, 5, 5]
    assert [jump_target(action, i) for i, action in enumerate(actions)] == [2, 4, 4, 4, 0]


def test_loop_inside_conditional_has_its_own_control_state():
    actions = flatten_gui_actions(
        (
            GuiAction(
                ActionCall(6),
                (
                    GuiAction(
                        ActionCall(2, (condition(),)),
                        (
                            GuiAction(
                                ActionCall(6),
                                (
                                    GuiAction(ActionCall(7, (condition(),))),
                                    GuiAction(ActionCall(8, (condition(),))),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )

    assert ids(actions) == [5, 5, 5, 5, 5, 5]
    assert [jump_target(action, i) for i, action in enumerate(actions)] == [5, 4, 1, 1, 5, 0]
