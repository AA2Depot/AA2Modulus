"""Lower bound events and statements to SIR events and GUI action trees."""

from __future__ import annotations

from ..hir.nodes import (
    BoundAction,
    BoundAssignment,
    BoundElse,
    BoundElseIf,
    BoundEvent,
    BoundFor,
    BoundIf,
    BoundLiteral,
    BoundLoop,
    BoundLoopControl,
    BoundRawAction,
    BoundRawEvent,
    BoundStatement,
)
from ..model.control_flow import (
    ACTION_CONDBREAK,
    ACTION_CONDCONTINUE,
    ACTION_ELSE,
    ACTION_ELSEIF,
    ACTION_FORLOOP,
    ACTION_IF,
    ACTION_LOOP,
    ACTION_SETVAR,
)
from ..model.native import ActionMetadata
from ..model.records import ActionCall, Event, Expression, GuiAction
from ..model.values import Value
from .expressions import lower_expression


def lower_event(node: BoundEvent | BoundRawEvent) -> Event:
    if isinstance(node, BoundRawEvent):
        return Event(
            node.identifier,
            tuple(lower_expression(item) for item in node.arguments),
            source_span=node.source_span,
            raw_reference=True,
        )
    return Event(
        node.metadata.id,
        tuple(lower_expression(item) for item in node.arguments),
        metadata=node.metadata,
        source_span=node.source_span,
    )


def lower_actions(nodes: tuple[BoundStatement, ...]) -> tuple[GuiAction, ...]:
    return tuple(action for node in nodes for action in _lower_statement(node))


def _gui(
    node: BoundStatement,
    identifier: int,
    arguments: tuple[Expression, ...],
    children: tuple[GuiAction, ...] = (),
    *,
    metadata: ActionMetadata | None = None,
    raw: bool = False,
) -> GuiAction:
    """One GUI node located at ``node``; raw actions mark both the node and its call."""

    return GuiAction(
        ActionCall(
            identifier,
            arguments,
            metadata=metadata,
            source_span=node.source_span,
            raw_reference=raw,
        ),
        children,
        source_span=node.source_span,
        raw_reference=raw,
    )


def _lower_statement(node: BoundStatement) -> tuple[GuiAction, ...]:
    if isinstance(node, BoundAction):
        arguments = tuple(lower_expression(item) for item in node.arguments)
        return (
            _gui(
                node,
                node.metadata.id,
                arguments,
                lower_actions(node.children),
                metadata=node.metadata,
            ),
        )
    if isinstance(node, BoundRawAction):
        arguments = tuple(lower_expression(item) for item in node.arguments)
        return (_gui(node, node.identifier, arguments, lower_actions(node.children), raw=True),)
    if isinstance(node, BoundAssignment):
        arguments = (lower_expression(node.variable), lower_expression(node.value))
        return (_gui(node, ACTION_SETVAR, arguments),)
    if isinstance(node, (BoundIf, BoundElseIf, BoundElse)):
        return _lower_conditional(node)
    if isinstance(node, BoundLoop):
        return (_gui(node, ACTION_LOOP, (), lower_actions(node.body)),)
    if isinstance(node, BoundFor):
        arguments = (
            lower_expression(node.variable),
            lower_expression(node.start),
            lower_expression(node.limit),
        )
        return (_gui(node, ACTION_FORLOOP, arguments, lower_actions(node.body)),)
    if isinstance(node, BoundLoopControl):
        condition = node.condition
        if condition is None:
            condition = BoundLiteral(Value.boolean(True), source_span=node.source_span)
        identifier = ACTION_CONDBREAK if node.keyword == "break" else ACTION_CONDCONTINUE
        return (_gui(node, identifier, (lower_expression(condition),)),)
    raise TypeError(f"unsupported bound statement: {node!r}")


def _lower_conditional(node: BoundIf | BoundElseIf | BoundElse) -> tuple[GuiAction, ...]:
    """An if becomes sibling If, ElseIf and Else GUI nodes, in source order."""

    if isinstance(node, BoundElseIf):
        return (
            _gui(
                node, ACTION_ELSEIF, (lower_expression(node.condition),), lower_actions(node.body)
            ),
        )
    if isinstance(node, BoundElse):
        return (_gui(node, ACTION_ELSE, (), lower_actions(node.body)),)
    result = [_gui(node, ACTION_IF, (lower_expression(node.condition),), lower_actions(node.body))]
    for branch in node.else_if:
        result.extend(_lower_statement(branch))
    if node.else_branch is not None:
        result.extend(_lower_statement(node.else_branch))
    return tuple(result)
