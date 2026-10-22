"""The incomplete call around a cursor and the argument type or role it expects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lark import Token

from ...context.operation import SourceContext
from ...language.types import CARD, CARD_ROLE, wire_type
from ...language.values import MemberForm
from ...metadata.identities import native_key
from ...model.native import ActionMetadata, ExpressionMetadata
from ...model.types import ValueType
from ...syntax.ast import SourceUnit
from ...syntax.recovery import BOUNDARY_TOKENS
from .receivers import MemberSite, member_forms, receiver
from .tokens import NAME_TOKENS, last_boundary, statement_context
from .type_hints import condition_context, surrounding_type, token_type

# Token types that start a fresh expression for comparison and operator typing.
_EXPRESSION_BREAKS = frozenset(
    {*BOUNDARY_TOKENS, "IF", "STANDALONE_ELSEIF", "AND_OP", "OR_OP", "COMMA", "EQUAL"}
)


@dataclass(frozen=True, slots=True)
class CallSite:
    opening: int
    name: str
    active: int
    parameter_sets: tuple[tuple[int, ...], ...]
    known: bool
    previous_arguments: tuple[tuple[Token, ...], ...]
    argument: tuple[Token, ...]
    parameter_roles: tuple[tuple[str | None, ...], ...]
    """Documentation roles parallel to ``parameter_sets`` (member arguments only)."""


def call_site(
    tokens: tuple[Token, ...],
    unit: SourceUnit | None,
    visible: Mapping[str, int],
    context: SourceContext,
) -> CallSite | None:
    """The innermost open call before the cursor and the parameter sets it may take."""

    call = matching_call(tokens)
    if call is None:
        return None
    opening, name, active = call
    before = tokens[: opening - 1]
    after_on = opening >= 2 and tokens[opening - 2].type == "ON"
    statement = statement_context(before)
    forms = () if after_on else member_call_forms(tokens, opening, name, unit, visible, context)
    if forms:
        # The receiver fills native slot 0, so argument i is native slot i + 1.
        parameter_sets = tuple(form.argument_types for form in forms)
        parameter_roles: tuple[tuple[str | None, ...], ...] = tuple(
            tuple(item.role for item in form.arguments) for form in forms
        )
        known = True
    elif after_on:
        event_entries = context.catalog.event_candidates(name)
        parameter_sets = tuple(item.parameter_types for item in event_entries)
        known = bool(event_entries)
    elif statement:
        parameter_sets, parameter_roles, known = _statement_parameters(name, unit, context)
    else:
        expected_return = expected_type_at(before, unit, visible, context)
        expression_entries = tuple(
            item
            for item in context.catalog.expression_candidates(name)
            if expected_return is None or item.return_type == expected_return
        )
        parameter_sets = tuple(item.parameter_types for item in expression_entries)
        parameter_roles = tuple(_flat_roles(context, item) for item in expression_entries)
        known = bool(context.catalog.expression_candidates(name))

    if after_on:
        parameter_roles = tuple((None,) * len(parameters) for parameters in parameter_sets)
    previous, argument = _split_arguments(tokens[opening + 1 :])
    return CallSite(
        opening,
        name,
        active,
        parameter_sets,
        known,
        previous,
        argument,
        parameter_roles,
    )


def _statement_parameters(
    name: str, unit: SourceUnit | None, context: SourceContext
) -> tuple[tuple[tuple[int, ...], ...], tuple[tuple[str | None, ...], ...], bool]:
    """Parameter sets, roles and known-ness of a statement call: macro first, then action."""

    macro = (
        next(
            (item for item in unit.macros if item.name.casefold() == name.casefold()),
            None,
        )
        if unit is not None
        else None
    )
    if macro is not None:
        return (
            (tuple(wire_type(item.type) for item in macro.parameters),),
            (tuple(CARD_ROLE if item.type is CARD else None for item in macro.parameters),),
            True,
        )
    action_entries = context.catalog.action_candidates(name)
    return (
        tuple(item.parameter_types for item in action_entries),
        tuple(_flat_roles(context, item) for item in action_entries),
        bool(action_entries),
    )


def _split_arguments(
    tokens: Sequence[Token],
) -> tuple[tuple[tuple[Token, ...], ...], tuple[Token, ...]]:
    """Completed top-level arguments and the argument being typed after the opening paren."""

    previous: list[tuple[Token, ...]] = []
    argument: list[Token] = []
    depth = 0
    for token in tokens:
        if token.type == "COMMA" and depth == 0:
            previous.append(tuple(argument))
            argument.clear()
        else:
            argument.append(token)
            if token.type == "LPAR":
                depth += 1
            elif token.type == "RPAR":
                depth -= 1
    return tuple(previous), tuple(argument)


def _flat_roles(
    context: SourceContext, entry: ActionMetadata | ExpressionMetadata
) -> tuple[str | None, ...]:
    """Policy roles of a flat target's slots (``[parameter_roles]``), ``None`` if untagged."""

    roles = context.source_policy.parameter_roles(native_key(entry))
    return roles if roles is not None else (None,) * len(entry.parameter_types)


def member_call_forms(
    tokens: tuple[Token, ...],
    opening: int,
    name: str,
    unit: SourceUnit | None,
    visible: Mapping[str, int],
    context: SourceContext,
) -> tuple[MemberForm, ...]:
    """Member forms of the ``receiver.Member(`` call opened at ``tokens[opening]``."""

    parts = name.split(".")
    member, path = parts[-1], parts[:-1]
    before = tokens[: opening - 1]
    found = receiver(before, path, visible, context)
    if found is None:
        return ()
    start, receiver_type = found
    statement = statement_context(before[:start])
    expected = None if statement else expected_type_at(before[:start], unit, visible, context)
    site = MemberSite(statement, receiver_type, expected, "", 0)
    return tuple(member_forms(context, site, member=member))


def usable_parameter_sets(
    call: CallSite, visible: Mapping[str, int], context: SourceContext
) -> tuple[tuple[int, ...], ...]:
    actual_types = tuple(
        token_type(argument, visible, context) for argument in call.previous_arguments
    )
    return tuple(
        parameters
        for parameters in call.parameter_sets
        if call.active < len(parameters)
        and all(
            actual is None or (index < len(parameters) and parameters[index] == actual)
            for index, actual in enumerate(actual_types)
        )
    )


def call_exhausted(
    tokens: tuple[Token, ...],
    unit: SourceUnit | None,
    visible: Mapping[str, int],
    context: SourceContext,
) -> bool:
    call = call_site(tokens, unit, visible, context)
    return call is not None and call.known and not usable_parameter_sets(call, visible, context)


def expected_type_at(
    tokens: tuple[Token, ...],
    unit: SourceUnit | None,
    visible: Mapping[str, int],
    context: SourceContext,
) -> int | None:
    call = call_site(tokens, unit, visible, context)
    if call is None:
        return _expected_type_outside_call(tokens, visible, context)
    active = call.active
    argument = call.argument
    if len(argument) >= 2 and argument[-1].type in {"EQUALITY_OP", "RELATIONAL_OP"}:
        known = token_type((argument[-2],), visible, context)
        if known is not None:
            return known
    choices = {parameters[active] for parameters in usable_parameter_sets(call, visible, context)}
    return next(iter(choices)) if len(choices) == 1 and ValueType.INVALID not in choices else None


def _expected_type_outside_call(
    tokens: tuple[Token, ...], visible: Mapping[str, int], context: SourceContext
) -> int | None:
    expression_start = last_boundary(tokens, _EXPRESSION_BREAKS) + 1
    comparison = next(
        (
            index
            for index in range(len(tokens) - 1, expression_start - 1, -1)
            if tokens[index].type in {"EQUALITY_OP", "RELATIONAL_OP"}
        ),
        None,
    )
    if comparison is not None and comparison:
        known = token_type((tokens[comparison - 1],), visible, context)
        if known is not None:
            return known
    if tokens and tokens[-1].type in {"ADD_OP", "MUL_OP"}:
        left_type = token_type((tokens[-2],), visible, context) if len(tokens) > 1 else None
        if left_type is not None:
            choices = {
                item.parameter_types[1]
                for item in context.source_policy.operator_candidates(str(tokens[-1]))
                if len(item.parameter_types) == 2 and item.parameter_types[0] == left_type
            }
            if len(choices) == 1:
                return next(iter(choices))
    if condition_context(tokens):
        segment = tokens[last_boundary(tokens) + 1 :]
        if segment and segment[-1].type == "NOT_OP":
            return ValueType.BOOL
        return None
    return surrounding_type(tokens, visible)


def expected_role_at(
    tokens: tuple[Token, ...],
    unit: SourceUnit | None,
    visible: Mapping[str, int],
    context: SourceContext,
) -> str | None:
    """The role of the argument the cursor starts, such as ``card`` in ``coach.AddLike(|``."""

    call = call_site(tokens, unit, visible, context)
    if call is None or call.argument:
        return None
    usable = set(usable_parameter_sets(call, visible, context))
    roles = {
        roles[call.active]
        for parameters, roles in zip(call.parameter_sets, call.parameter_roles, strict=True)
        if parameters in usable
    }
    return next(iter(roles)) if len(roles) == 1 else None


def matching_call(tokens: tuple[Token, ...]) -> tuple[int, str, int] | None:
    depth = 0
    candidates: list[int] = []
    for index in range(len(tokens) - 1, -1, -1):
        token = tokens[index]
        if token.type == "RPAR":
            depth += 1
        elif token.type == "LPAR":
            if depth == 0:
                candidates.append(index)
            else:
                depth -= 1
    opening = next(
        (index for index in candidates if index > 0 and tokens[index - 1].type in NAME_TOKENS),
        -1,
    )
    if opening < 1:
        return None
    callee = tokens[opening - 1]
    active_argument = 0
    depth = 0
    for token in tokens[opening + 1 :]:
        if token.type == "LPAR":
            depth += 1
        elif token.type == "RPAR":
            depth -= 1
        elif token.type == "COMMA" and depth == 0:
            active_argument += 1
    return opening, str(callee), active_argument
