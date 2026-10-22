"""Write targets inside macro and template definitions."""

from __future__ import annotations

from ...hir.nodes import (
    BoundExpression,
    BoundRawExpression,
    BoundRawVariable,
    BoundVariable,
)
from ...model.control_flow import (
    ACTION_CONDBREAK,
    ACTION_CONDCONTINUE,
    ACTION_FORLOOP,
    ACTION_SETVAR,
)
from ...syntax.ast import (
    SourceAction,
    SourceMemberAction,
)
from .reporting import raise_error
from .state import BindContext


def check_macro_action(
    context: BindContext, node: SourceAction | SourceMemberAction, identifier: int
) -> None:
    if (
        context.template_definition is not None
        and identifier in {ACTION_CONDBREAK, ACTION_CONDCONTINUE}
        and context.loop_depth == 0
    ):
        raise_error(
            context, node, "TEMPLATE_LOOP_SCOPE", "loop control requires a loop in its own template"
        )
    if context.macro_definition is None:
        return
    if identifier in {ACTION_SETVAR, ACTION_FORLOOP}:
        raise_error(
            context,
            node,
            "MACRO_PARAMETER_WRITE",
            "assignment-target actions are forbidden in macro definitions",
        )
    if identifier in {ACTION_CONDBREAK, ACTION_CONDCONTINUE} and context.loop_depth == 0:
        raise_error(
            context,
            node,
            "MACRO_LOOP_SCOPE",
            "loop control requires a loop in its own macro definition",
        )


def check_template_target(
    context: BindContext,
    node: SourceAction | SourceMemberAction,
    identifier: int,
    arguments: tuple[BoundExpression, ...],
) -> None:
    if context.template_definition is None or identifier not in {ACTION_SETVAR, ACTION_FORLOOP}:
        return
    target = arguments[0] if arguments else None
    name: str | None = None
    if isinstance(target, BoundVariable):
        name = target.name
    elif isinstance(target, BoundRawExpression) and isinstance(target.payload, BoundRawVariable):
        name = target.payload.name
    if name is not None and context.is_slot(name):
        raise_error(
            context,
            node,
            "TEMPLATE_SLOT_WRITE",
            "assignment-target actions cannot write value slots",
        )
    if name is None or name not in context.locals:
        raise_error(
            context, node, "TEMPLATE_CAPTURE", "assignment-target actions require a template local"
        )
