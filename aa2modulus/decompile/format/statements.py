"""Action and event rendering: branches, loops, assignments, member calls and raw fallbacks."""

from __future__ import annotations

from ...core.source_names import is_source_name
from ...language.types import member_parameter_types, parameter_types
from ...language.values import MemberForm
from ...model.control_flow import (
    ACTION_CONDBREAK,
    ACTION_CONDCONTINUE,
    ACTION_ELSE,
    ACTION_ELSEIF,
    ACTION_FORLOOP,
    ACTION_IF,
    ACTION_LOOP,
    ACTION_SETVAR,
)
from ...model.native import ActionMetadata, EventMetadata
from ...model.records import Event, GuiAction
from ...model.types import EXPR_CONSTANT, EXPR_VAR, ValueType
from .cards import card_text
from .context import (
    FormatContext,
    assignment_name,
    catalog_name,
    declaration_name,
)
from .expressions import expression_text, member_is_unique, positioned_text, receiver_text
from .fallbacks import (
    action_fallback_reason,
    event_fallback_reason,
    same_signature,
    signature_fallback_reason,
)


def _member_action_lines(
    action: GuiAction, member: MemberForm, context: FormatContext, indent: int
) -> list[str]:
    call = action.action
    pad = " " * indent
    reason: str | None = None
    if call.raw_reference:
        reason = "explicit raw provenance"
    else:
        metadata = call.metadata or context.metadata.action(call.id)
        if metadata is None:
            reason = f"unknown identity: action id {call.id}"
        elif not same_signature(call.parameters, metadata.parameter_types):
            reason = signature_fallback_reason(
                "action", call.id, call.parameters, metadata.parameter_types
            )
        elif member.parameter_types != metadata.parameter_types:
            reason = "declaration mismatch: member form does not match its target"
        elif action.children:
            reason = f"incompatible signature: member action {member.name!r} cannot take a block"
        elif not member_is_unique(member, context, None):
            reason = f"ambiguous source spelling: member {member.name!r} has no unique overload"
    if reason is None:
        mark = len(context.diagnostics)
        receiver = receiver_text(call.parameters[0], member, context)
        if receiver is None:
            del context.diagnostics[mark:]
            reason = f"member {member.name!r} receiver cannot be written as a receiver"
        else:
            arguments = ", ".join(
                positioned_text(item, context, expected, wire)
                for item, expected, wire in zip(
                    call.parameters[1:],
                    member_parameter_types(member)[1:],
                    member.argument_types,
                    strict=False,
                )
            )
            return [f"{pad}{receiver}.{member.name}({arguments});"]
    return _raw_action_lines(action, context, indent, reason)


def _action_arguments(action: GuiAction, context: FormatContext) -> list[str]:
    metadata = action.action.metadata or context.metadata.action(action.action.id)
    wires = () if metadata is None else metadata.parameter_types
    sources = () if metadata is None else parameter_types(context.policy, metadata)
    arguments = [
        positioned_text(
            item,
            context,
            sources[index] if index < len(sources) else None,
            wires[index] if index < len(wires) else None,
        )
        for index, item in enumerate(action.action.parameters)
    ]
    while arguments:
        index = len(arguments) - 1
        default = context.policy.action_default(action.action.id, index)
        expression = action.action.parameters[index]
        if (
            default is not None
            and not expression.raw_reference
            and expression.id == EXPR_CONSTANT
            and expression.constant == default.value
        ):
            arguments.pop()
            continue
        break
    return arguments


def _raw_action_lines(
    action: GuiAction,
    context: FormatContext,
    indent: int,
    reason: str | None = None,
) -> list[str]:
    context.raw_fallback(action.action, reason or action_fallback_reason(action, context))
    pad = " " * indent
    arguments = ", ".join(expression_text(item, context) for item in action.action.parameters)
    if not action.children and not arguments:
        return [f"{pad}raw_action {action.action.id};"]
    lines = [f"{pad}raw_action {action.action.id}({arguments})"]
    if action.children:
        lines[-1] += " {"
        lines.extend(action_sequence_lines(action.children, context, indent + 2))
        lines.append(f"{pad}}}")
    else:
        lines[-1] += ";"
    return lines


def _flow_signature_matches(action: GuiAction, context: FormatContext) -> bool:
    call = action.action
    if call.raw_reference:
        return False
    metadata = call.metadata or context.metadata.action(call.id)
    if metadata is None or len(call.parameters) != len(metadata.parameter_types):
        return False
    return all(
        expected is ValueType.INVALID or expression.return_type == expected
        for expression, expected in zip(call.parameters, metadata.parameter_types, strict=True)
    )


def _branch_signature_matches(action: GuiAction, context: FormatContext) -> bool:
    call = action.action
    if call.raw_reference:
        return False
    expected = () if call.id == ACTION_ELSE else (ValueType.BOOL,)
    metadata = context.metadata.action(call.id)
    if metadata is None or metadata.parameter_types != expected:
        return False
    if call.metadata is not None and (
        call.metadata.id != call.id or call.metadata.parameter_types != expected
    ):
        return False
    return same_signature(call.parameters, expected)


def _branch_lines(
    action: GuiAction, context: FormatContext, indent: int, keyword: str
) -> list[str]:
    pad = " " * indent
    if action.action.id == ACTION_ELSE:
        if keyword == "Else" and not action.children:
            return [f"{pad}Else;"]
        head = keyword
    else:
        condition = expression_text(
            action.action.parameters[0], context, expected_type=ValueType.BOOL
        )
        head = f"{keyword} ({condition})"
    lines = [f"{pad}{head} {{"]
    lines.extend(action_sequence_lines(action.children, context, indent + 2))
    lines.append(f"{pad}}}")
    return lines


def action_sequence_lines(
    actions: tuple[GuiAction, ...], context: FormatContext, indent: int
) -> list[str]:
    """Project sibling branches without changing their records or children."""

    lines: list[str] = []
    index = 0
    while index < len(actions):
        action = actions[index]
        if action.action.id != ACTION_IF or not _branch_signature_matches(action, context):
            lines.extend(context.allow_lines((action,), indent))
            lines.extend(_action_lines(action, context, indent))
            index += 1
            continue
        members = [action]
        chain = _branch_lines(action, context, indent, "if")
        index += 1
        while index < len(actions):
            branch = actions[index]
            if branch.action.id not in {ACTION_ELSEIF, ACTION_ELSE} or not (
                _branch_signature_matches(branch, context)
            ):
                break
            keyword = "else" if branch.action.id == ACTION_ELSE else "else if"
            attached = _branch_lines(branch, context, indent, keyword)
            chain[-1] += " " + attached[0].lstrip()
            chain.extend(attached[1:])
            members.append(branch)
            index += 1
            if branch.action.id == ACTION_ELSE:
                break
        # Branch conditions belong to the one `if` statement the chain parses as.
        lines.extend(context.allow_lines(tuple(members), indent))
        lines.extend(chain)
    return lines


def _action_metadata(
    action: GuiAction,
    context: FormatContext,
) -> ActionMetadata | None:
    call = action.action
    if call.raw_reference:
        return None
    metadata = call.metadata or context.metadata.action(call.id)
    if metadata is None:
        return None
    if not same_signature(call.parameters, metadata.parameter_types):
        return None
    name = catalog_name(context, "action", call.id)
    if name is None:
        return None
    if not is_source_name(name):
        return None
    candidates = context.catalog.action_candidates(name)
    if len(candidates) != 1 or candidates[0].id != call.id:
        return None
    return metadata


def _event_metadata(
    event: Event,
    context: FormatContext,
) -> EventMetadata | None:
    if event.raw_reference:
        return None
    metadata = event.metadata or context.metadata.event(event.id)
    if metadata is None or not same_signature(event.parameters, metadata.parameter_types):
        return None
    name = catalog_name(context, "event", event.id)
    if name is None:
        return None
    if not is_source_name(name):
        return None
    if not is_source_name(name):
        return None
    candidates = context.catalog.event_candidates(name)
    if len(candidates) != 1 or candidates[0].id != event.id:
        return None
    return metadata


def _action_lines(action: GuiAction, context: FormatContext, indent: int) -> list[str]:
    identifier = action.action.id
    if identifier in {ACTION_IF, ACTION_ELSEIF, ACTION_ELSE}:
        if not _branch_signature_matches(action, context):
            return _raw_action_lines(action, context, indent)
        keyword = {ACTION_IF: "if", ACTION_ELSEIF: "ElseIf", ACTION_ELSE: "Else"}[identifier]
        return _branch_lines(action, context, indent, keyword)
    if _flow_signature_matches(action, context):
        for build in (_loop_lines, _for_lines, _jump_lines, _assignment_lines):
            lines = build(action, context, indent)
            if lines is not None:
                return lines
    member = context.catalog.member_form("action", identifier)
    if member is not None:
        return _member_action_lines(action, member, context, indent)
    metadata = _action_metadata(action, context)
    if metadata is None:
        return _raw_action_lines(action, context, indent)
    name = catalog_name(context, "action", identifier)
    assert name is not None
    arguments = ", ".join(_action_arguments(action, context))
    return _block_lines(f"{' ' * indent}{name}({arguments})", action, context, indent)


def _block_lines(head: str, action: GuiAction, context: FormatContext, indent: int) -> list[str]:
    """``head`` followed by the action's children as a block, or ``;`` when it has none."""

    if not action.children:
        return [head + ";"]
    lines = [head + " {"]
    lines.extend(action_sequence_lines(action.children, context, indent + 2))
    lines.append(f"{' ' * indent}}}")
    return lines


def _loop_lines(action: GuiAction, context: FormatContext, indent: int) -> list[str] | None:
    if action.action.id != ACTION_LOOP or action.action.parameters:
        return None
    pad = " " * indent
    lines = [f"{pad}loop {{"]
    lines.extend(action_sequence_lines(action.children, context, indent + 2))
    lines.append(f"{pad}}}")
    return lines


def _for_lines(action: GuiAction, context: FormatContext, indent: int) -> list[str] | None:
    if action.action.id != ACTION_FORLOOP or len(action.action.parameters) != 3:
        return None
    pad = " " * indent
    target, start, limit = action.action.parameters
    if not (
        target.id == EXPR_VAR
        and target.variable_name is not None
        and not target.raw_reference
        and target.return_type == ValueType.INT
        and context.variables.get(target.variable_name) == ValueType.INT
        and start.return_type == ValueType.INT
        and limit.return_type == ValueType.INT
    ):
        return None
    start_text = expression_text(start, context, expected_type=ValueType.INT)
    if target.variable_name in context.cards:
        start_text = card_text(start, start_text, context)
    lines = [
        (
            f"{pad}for {declaration_name(target.variable_name, context)} from "
            f"{start_text} to "
            f"{expression_text(limit, context, expected_type=ValueType.INT)} {{"
        )
    ]
    lines.extend(action_sequence_lines(action.children, context, indent + 2))
    lines.append(f"{pad}}}")
    return lines


def _jump_lines(action: GuiAction, context: FormatContext, indent: int) -> list[str] | None:
    identifier = action.action.id
    if not (
        identifier in {ACTION_CONDBREAK, ACTION_CONDCONTINUE}
        and len(action.action.parameters) == 1
        and not action.children
        and action.action.parameters[0].return_type == ValueType.BOOL
    ):
        return None
    keyword = "break" if identifier == ACTION_CONDBREAK else "continue"
    condition = action.action.parameters[0]
    suffix = ""
    if not (
        condition.id == EXPR_CONSTANT
        and condition.constant is not None
        and condition.constant.type is ValueType.BOOL
        and condition.constant.value is True
        and not condition.raw_reference
    ):
        suffix = f" if {expression_text(condition, context, expected_type=ValueType.BOOL)}"
    return [f"{' ' * indent}{keyword}{suffix};"]


def _assignment_lines(action: GuiAction, context: FormatContext, indent: int) -> list[str] | None:
    if not (
        action.action.id == ACTION_SETVAR
        and len(action.action.parameters) == 2
        and not action.children
    ):
        return None
    target = action.action.parameters[0]
    if not (
        target.id == EXPR_VAR
        and target.variable_name is not None
        and not target.raw_reference
        and context.variables.get(target.variable_name) == target.return_type
        and action.action.parameters[1].return_type == target.return_type
    ):
        return None
    value = action.action.parameters[1]
    value_text = expression_text(value, context, expected_type=target.return_type)
    if target.variable_name in context.cards:
        value_text = card_text(value, value_text, context)
    return [f"{' ' * indent}{assignment_name(target.variable_name, context)} = {value_text};"]


def event_line(event: Event, context: FormatContext, indent: int) -> str:
    pad = " " * indent
    metadata = _event_metadata(event, context)
    if metadata is None:
        context.raw_fallback(event, event_fallback_reason(event, context))
        arguments = ", ".join(expression_text(item, context) for item in event.parameters)
        return (
            f"{pad}raw_event {event.id}({arguments});"
            if arguments
            else f"{pad}raw_event {event.id};"
        )
    name = catalog_name(context, "event", event.id)
    assert name is not None
    arguments = ", ".join(
        expression_text(item, context, expected_type=expected)
        for item, expected in zip(event.parameters, metadata.parameter_types, strict=False)
    )
    suffix = f"({arguments})" if arguments else ""
    return f"{pad}on {name}{suffix};"
