"""Statements and events (one recursive group)."""

from __future__ import annotations

from dataclasses import replace

from ...core.diagnostics import SourceFix
from ...core.locations import SourceSpan
from ...hir.nodes import (
    BoundAction,
    BoundAssignment,
    BoundElse,
    BoundElseIf,
    BoundEvent,
    BoundFor,
    BoundIf,
    BoundLoop,
    BoundLoopControl,
    BoundRawAction,
    BoundRawEvent,
    BoundStatement,
    BoundVariable,
)
from ...language.types import (
    CARD,
    SourceType,
    parameter_types,
)
from ...model.control_flow import (
    ACTION_FORLOOP,
    ACTION_LOOP,
    ACTION_SETVAR,
)
from ...model.native import ActionMetadata
from ...model.types import ValueType
from ...syntax.ast import (
    SourceAction,
    SourceAssignment,
    SourceElse,
    SourceElseIf,
    SourceEvent,
    SourceExpression,
    SourceFor,
    SourceIf,
    SourceLiteral,
    SourceLoop,
    SourceLoopControl,
    SourceMemberAction,
    SourceName,
    SourceStatement,
)
from ...syntax.hints import FOREIGN_KEYWORD_HELP
from .constants import constant_entry
from .declarations import is_protected, protected_help, protected_message
from .expressions import (
    bind_arguments,
    bind_expression,
    bind_member_arguments,
)
from .macro_calls import bind_macro_call
from .members import bind_member_form, dotted_receiver
from .reporting import (
    bind_or_record,
    join_help,
    node_span,
    raise_error,
    record_member_reference,
    record_reference,
    record_variable_reference,
)
from .rewrites import member_fixes, receiver_text, root_fixes, while_fixes
from .state import BindContext, Poisoned, SourceBindingError
from .suggestions import retired_hint, root_hint
from .targets import check_macro_action, check_template_target


def _bind_member_action(
    context: BindContext,
    node: SourceAction | SourceMemberAction,
    receiver: SourceExpression,
    member: str,
    member_span: SourceSpan | None,
) -> BoundAction:
    if isinstance(node, SourceMemberAction) and not node.has_parentheses:
        text = f"{receiver_text(receiver)}.{member}"
        raise_error(
            context,
            node,
            "MEMBER_KIND",
            f"{text!r} is not a statement; actions are calls",
            help=f"write '{text}(...)'",
        )
    if isinstance(node, SourceAction) and (node.has_block or node.children):
        raise_error(context, node, "MEMBER_ACTION_BLOCK", "member actions cannot take a block")
    form = bind_member_form(
        context, node, receiver, member, len(node.arguments), action=True, expected=None
    )
    target = context.catalog.member_target(form)
    assert isinstance(target, ActionMetadata)
    check_macro_action(context, node, target.id)
    bound = bind_member_arguments(context, form, receiver, node.arguments)
    check_template_target(context, node, target.id, bound)
    record_member_reference(context, member, member_span, target, form)
    return BoundAction(metadata=target, arguments=bound, children=(), source_span=node_span(node))


def bind_event(context: BindContext, node: SourceEvent) -> BoundEvent | BoundRawEvent:
    if node.identifier is not None:
        return BoundRawEvent(
            identifier=node.identifier,
            arguments=bind_arguments(context, ((item, None) for item in node.arguments)),
            source_span=node_span(node),
        )
    candidates = context.catalog.event_candidates(node.name or "")
    if len(candidates) != 1:
        raise_error(
            context,
            node,
            "UNKNOWN_EVENT_NAME",
            f"no unique event {node.name!r}",
            help=join_help(
                root_hint(context, node.name or "", "event"),
                retired_hint(context, node.name or "", "event"),
            ),
            fixes=root_fixes(context, node.name or "", node.name_span, "event"),
        )
    entry = candidates[0]
    record_reference(context, node.name or "", node, metadata=entry)
    if len(entry.parameter_types) != len(node.arguments):
        raise_error(
            context, node, "EVENT_ARITY", f"event {node.name!r} has the wrong argument count"
        )
    return BoundEvent(
        metadata=entry,
        arguments=bind_arguments(context, zip(node.arguments, entry.parameter_types, strict=False)),
        source_span=node_span(node),
    )


def bind_statement(context: BindContext, node: SourceStatement) -> tuple[BoundStatement, ...]:
    context.depth += 1
    context.nesting += 1
    try:
        return bind_or_record(context, _bind_statement_inner, context, node) or ()
    finally:
        context.depth -= 1
        context.nesting -= 1


def _bind_statement_inner(
    context: BindContext, node: SourceStatement
) -> tuple[BoundStatement, ...]:
    if (
        isinstance(node, SourceAction)
        and node.name is not None
        and node.name.casefold() in context.macros
    ):
        if context.collector is not None and (
            node.name.casefold() in context.collector.poisoned_macros
        ):
            raise Poisoned
        return bind_macro_call(context, node)
    if isinstance(node, SourceAssignment):
        return (_bind_assignment(context, node),)
    if isinstance(node, SourceAction):
        return (_bind_action(context, node),)
    if isinstance(node, SourceMemberAction):
        return (_bind_member_action(context, node, node.receiver, node.member, node.name_span),)
    if isinstance(node, SourceElseIf):
        return (_bind_else_if(context, node),)
    if isinstance(node, SourceElse):
        return (_bind_else(context, node),)
    if isinstance(node, SourceIf):
        return (_bind_if(context, node),)
    if isinstance(node, SourceLoop):
        return (_bind_loop(context, node),)
    if isinstance(node, SourceFor):
        return (_bind_for(context, node),)
    if isinstance(node, SourceLoopControl):
        return (_bind_loop_control(context, node),)
    raise_error(context, node, "UNSUPPORTED_STATEMENT", f"unsupported source statement {node!r}")


def _reject_constant_target(
    context: BindContext, name: str, span: SourceSpan | None, what: str, *, assignment: bool = False
) -> None:
    entry = constant_entry(
        context,
        name,
        SourceName(name, source_span=span),
        use="assignment" if assignment else "target",
    )
    if entry is not None:
        raise_error(
            context,
            SourceName(name, source_span=span),
            "CONST_ASSIGNMENT",
            f"constant {name!r} cannot be {what}",
        )


def _bind_assignment(context: BindContext, node: SourceAssignment) -> BoundAssignment:
    if not node.explicit_variable:
        if is_protected(context, node.target):
            raise_error(
                context,
                replace(node, source_span=node.target_span or node_span(node)),
                "PROTECTED_NAME",
                f"{node.target!r} is a protected built-in name and cannot be assigned",
                help=f'assign a native variable of this name with variable("{node.target}")',
                fixes=()
                if node.target_span is None
                else (
                    SourceFix(
                        f'Write variable("{node.target}")',
                        node.target_span,
                        f'variable("{node.target}")',
                    ),
                ),
            )
        _reject_constant_target(context, node.target, node.target_span, "assigned", assignment=True)
    if context.template_definition is not None:
        if context.is_slot(node.target):
            raise_error(
                context, node, "TEMPLATE_SLOT_WRITE", "template value slots cannot be assigned"
            )
        if node.target not in context.locals:
            raise_error(
                context,
                node,
                "TEMPLATE_CAPTURE",
                "template assignment targets require a declared local",
            )
    if context.macro_definition is not None:
        code = "MACRO_PARAMETER_WRITE" if node.target in context.locals else "MACRO_CAPTURE"
        raise_error(
            context, node, code, "macro definitions cannot assign variables or value parameters"
        )
    value_type = context.variable_type(node.target)
    if value_type is None:
        help, fixes = context.undeclared_help(node.target, _value_type(context, node.value))
        raise_error(
            context,
            node,
            "UNDEFINED_VARIABLE",
            f"undefined assignment target {node.target!r}",
            help=help,
            fixes=fixes,
        )
    record_variable_reference(context, node.target, node, value_type)
    return BoundAssignment(
        variable=BoundVariable(name=node.target, type=value_type, source_span=node_span(node)),
        value=bind_expression(context, node.value, value_type),
        source_span=node_span(node),
    )


def _bind_action(context: BindContext, node: SourceAction) -> BoundAction | BoundRawAction:
    if node.identifier is not None:
        check_macro_action(context, node, node.identifier)
        bound_arguments = bind_arguments(context, ((item, None) for item in node.arguments))
        check_template_target(context, node, node.identifier, bound_arguments)
        children = bind_children(
            context, node.children, loop=node.identifier in {ACTION_LOOP, ACTION_FORLOOP}
        )
        return BoundRawAction(
            identifier=node.identifier,
            arguments=bound_arguments,
            children=children,
            source_span=node_span(node),
        )

    candidates = context.catalog.action_candidates(node.name or "")
    if not candidates:
        dotted = dotted_receiver(context, node.name or "", node.name_span)
        if dotted is not None:
            receiver, member, member_span = dotted
            return _bind_member_action(context, node, receiver, member, member_span)
    if len(candidates) != 1:
        raise_error(
            context,
            node,
            "UNKNOWN_ACTION_NAME",
            f"no unique action {node.name!r}",
            help=join_help(
                root_hint(context, node.name or "", "action"),
                retired_hint(context, node.name or "", "action", arguments=node.arguments),
                FOREIGN_KEYWORD_HELP.get(node.name or "", "") if not candidates else "",
            ),
            fixes=root_fixes(context, node.name or "", node.name_span, "action")
            + member_fixes(context, node, "action")
            + (() if candidates else while_fixes(node)),
        )
    action = candidates[0]
    record_reference(context, node.name or "", node, metadata=action)
    check_macro_action(context, node, action.id)
    if action.id in {ACTION_SETVAR, ACTION_FORLOOP} and isinstance(
        first := next(iter(node.arguments), None), SourceName
    ):
        _reject_constant_target(context, first.name, first.source_span, "assigned")
    arguments = list(node.arguments)
    while len(arguments) < len(action.parameter_types):
        default = context.source_policy.action_default(action.id, len(arguments))
        if default is None:
            raise_error(
                context, node, "ACTION_ARITY", f"action {node.name!r} is missing an argument"
            )
        arguments.append(SourceLiteral(default.value.value, source_span=node_span(node)))
    if len(arguments) != len(action.parameter_types):
        raise_error(
            context, node, "ACTION_ARITY", f"action {node.name!r} has the wrong argument count"
        )
    bound_arguments = bind_arguments(
        context,
        (
            (
                item,
                None
                if context.template_definition is not None
                and action.id in {ACTION_SETVAR, ACTION_FORLOOP}
                and expected == ValueType.INVALID
                else expected,
            )
            for item, expected in zip(
                arguments, parameter_types(context.source_policy, action), strict=False
            )
        ),
    )
    check_template_target(context, node, action.id, bound_arguments)
    children = bind_children(
        context, node.children, loop=action.id in {ACTION_LOOP, ACTION_FORLOOP}
    )
    return BoundAction(
        metadata=action,
        arguments=bound_arguments,
        children=children,
        source_span=node_span(node),
    )


def _bind_if(context: BindContext, node: SourceIf) -> BoundIf:
    body = tuple(child for item in node.body for child in bind_statement(context, item))
    context.depth += 1
    context.nesting += 1
    try:
        else_if = tuple(_bind_else_if(context, branch) for branch in node.else_if)
        else_branch = (
            _bind_else(context, node.else_branch) if node.else_branch is not None else None
        )
    finally:
        context.depth -= 1
        context.nesting -= 1
    return BoundIf(
        condition=bind_expression(context, node.condition, ValueType.BOOL),
        body=body,
        else_if=else_if,
        else_branch=else_branch,
        source_span=node_span(node),
    )


def _bind_else_if(context: BindContext, node: SourceElseIf) -> BoundElseIf:
    return BoundElseIf(
        condition=bind_expression(context, node.condition, ValueType.BOOL),
        body=tuple(child for item in node.body for child in bind_statement(context, item)),
        source_span=node_span(node),
    )


def _bind_else(context: BindContext, node: SourceElse) -> BoundElse:
    return BoundElse(
        body=tuple(child for item in node.body for child in bind_statement(context, item)),
        source_span=node_span(node),
    )


def _bind_loop(context: BindContext, node: SourceLoop) -> BoundLoop:
    return BoundLoop(
        body=bind_children(context, node.body, loop=True),
        source_span=node_span(node),
    )


def _bind_for(context: BindContext, node: SourceFor) -> BoundFor:
    if is_protected(context, node.target) and not node.quoted_name:
        raise_error(
            context,
            replace(node, source_span=node.target_span or node_span(node)),
            "PROTECTED_NAME",
            protected_message(node.target),
            help=protected_help(node.target),
        )
    _reject_constant_target(context, node.target, node.target_span, "used as a for-loop target")
    if context.template_definition is not None:
        if context.is_slot(node.target):
            raise_error(
                context,
                node,
                "TEMPLATE_SLOT_WRITE",
                "template for-loop targets cannot be value slots",
            )
        if node.target not in context.locals:
            raise_error(
                context,
                node,
                "TEMPLATE_CAPTURE",
                "template for-loop targets require a declared local",
            )
    if context.macro_definition is not None:
        code = "MACRO_PARAMETER_WRITE" if node.target in context.locals else "MACRO_CAPTURE"
        raise_error(context, node, code, "macro definitions cannot write a for-loop target")
    variable_type = context.variable_type(node.target)
    if variable_type is None:
        help, fixes = context.undeclared_help(node.target, ValueType.INT)
        raise_error(
            context,
            node,
            "UNDEFINED_VARIABLE",
            f"undefined for-loop target {node.target!r}",
            help=help,
            fixes=fixes,
        )
    if variable_type is not CARD and variable_type != ValueType.INT:
        raise_error(
            context, node, "FOR_LOOP_TARGET_TYPE", "for-loop target must have type int or card"
        )
    record_variable_reference(context, node.target, node, variable_type)
    return BoundFor(
        variable=BoundVariable(name=node.target, type=variable_type, source_span=node_span(node)),
        start=bind_expression(context, node.start, variable_type),
        limit=bind_expression(context, node.limit, ValueType.INT),
        body=bind_children(context, node.body, loop=True),
        source_span=node_span(node),
    )


def _bind_loop_control(context: BindContext, node: SourceLoopControl) -> BoundLoopControl:
    if node.keyword not in {"break", "continue"}:
        raise_error(context, node, "INVALID_LOOP_CONTROL", f"unknown loop control {node.keyword!r}")
    if context.macro_definition is not None and context.loop_depth == 0:
        raise_error(
            context,
            node,
            "MACRO_LOOP_SCOPE",
            "loop control requires a loop in its own macro definition",
        )
    if context.template_definition is not None and context.loop_depth == 0:
        raise_error(
            context, node, "TEMPLATE_LOOP_SCOPE", "loop control requires a loop in its own template"
        )
    return BoundLoopControl(
        keyword=node.keyword,
        condition=(
            None
            if node.condition is None
            else bind_expression(context, node.condition, ValueType.BOOL)
        ),
        source_span=node_span(node),
    )


def bind_children(
    context: BindContext, nodes: tuple[SourceStatement, ...], *, loop: bool = False
) -> tuple[BoundStatement, ...]:
    context.loop_depth += int(loop)
    try:
        return tuple(child for node in nodes for child in bind_statement(context, node))
    finally:
        context.loop_depth -= int(loop)


def _value_type(context: BindContext, value: SourceExpression) -> SourceType | None:
    """The type an assigned value binds to on its own, if it binds at all."""

    try:
        return bind_expression(context.fork_references(), value, None).type
    except SourceBindingError:
        return None
