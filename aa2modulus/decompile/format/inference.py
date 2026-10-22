"""Choose which variables to declare ``card`` so rendering needs fewer ``Card(...)``."""

from __future__ import annotations

from ...language.types import CARD, CARD_ROLE, SourceType, member_parameter_types, parameter_types
from ...model.control_flow import (
    ACTION_FORLOOP,
    ACTION_SETVAR,
)
from ...model.native import ActionMetadata, ExpressionMetadata
from ...model.records import Expression, GuiAction, Module
from ...model.types import EXPR_PAYLOAD_MARKERS, EXPR_VAR, TypeId, ValueType
from .cards import is_int_literal
from .context import (
    FormatContext,
    operator_text,
)
from .expressions import expression_text

type CardKey = tuple[int | None, str]
"""A card candidate: ``(None, name)`` for a module global, ``(trigger, name)`` for a local."""


def _source_positions(
    node: Expression | GuiAction, context: FormatContext
) -> tuple[tuple[Expression, SourceType | None], ...]:
    """Each native parameter of ``node`` with its source type (``CARD`` for card slots)."""

    metadata: ActionMetadata | ExpressionMetadata | None
    if isinstance(node, GuiAction):
        parameters = node.action.parameters
        member = context.catalog.member_form("action", node.action.id)
        metadata = node.action.metadata or context.metadata.action(node.action.id)
    else:
        parameters = node.parameters
        member = context.catalog.member_form("expression", node.id, node.return_type)
        metadata = (
            None
            if node.id in EXPR_PAYLOAD_MARKERS
            else node.metadata or context.metadata.expression(node.return_type, node.id)
        )
    kinds: tuple[SourceType | None, ...] = ()
    if member is not None:
        kinds = member_parameter_types(member)
    elif metadata is not None:
        kinds = parameter_types(context.policy, metadata)
    if len(kinds) != len(parameters):
        kinds = (None,) * len(parameters)
    return tuple(zip(parameters, kinds, strict=True))


class CardInference:
    """Variables to declare ``card``, choosing the typing that needs fewer ``Card(...)``.

    A variable is a candidate when it appears in a card slot (a member receiver or
    card argument) or is compared with a card-valued call. Declared ``int``, each
    such use is converted; declared ``card``, each value written to it (default,
    assignment, ``for`` start) that is neither an int literal nor card-valued is
    converted instead. Candidates whose writes would cost more than their uses are
    dropped until no cost changes. Rendering converts every remaining int in a
    card position, so the result always binds; inference only reduces conversions.
    """

    def __init__(
        self,
        module: Module,
        context: FormatContext,
        scopes: tuple[dict[str, TypeId], ...],
        own: set[str],
    ) -> None:
        self._module = module
        self._context = context
        self._scopes = scopes
        self._own = own
        self._used: dict[CardKey, int] = {}
        self._writes: dict[CardKey, list[tuple[int, Expression]]] = {}
        self._calls: dict[int, bool] = {}

    def infer(self) -> frozenset[CardKey]:
        self._collect()
        cards = set(self._used)
        changed = True
        while changed:
            changed = False
            for candidate in sorted(cards, key=lambda item: (item[0] is not None, item)):
                conversions = sum(
                    not self._is_card_value(index, value, cards)
                    for index, value in self._writes.get(candidate, ())
                )
                if conversions > self._used[candidate]:
                    cards.discard(candidate)
                    changed = True
        return frozenset(cards)

    def _collect(self) -> None:
        for index, trigger in enumerate(self._module.triggers):
            for local in trigger.variables:
                found = self._key(index, local.name)
                if found is not None and found[0] == index:
                    self._writes.setdefault(found, []).append((index, local.default_expression))
                self._visit(index, local.default_expression)
            for event in trigger.events:
                for parameter in event.parameters:
                    self._visit(index, parameter)
            for action in trigger.gui_actions:
                self._visit(index, action)

    def _key(self, index: int, name: str | None) -> CardKey | None:
        if name is None or self._scopes[index].get(name) != ValueType.INT:
            return None
        if name in self._own:
            return (None, name)
        return None if name in self._scopes[-1] else (index, name)

    def _variable(self, index: int, expression: Expression) -> CardKey | None:
        if expression.raw_reference or expression.id != EXPR_VAR:
            return None
        if expression.return_type != ValueType.INT:
            return None
        return self._key(index, expression.variable_name)

    def _is_card_call(self, index: int, expression: Expression) -> bool:
        context = self._context
        if (
            expression.raw_reference
            or expression.return_type != ValueType.INT
            or expression.id in EXPR_PAYLOAD_MARKERS
            or context.policy.expression_result_role(ValueType.INT, expression.id) != CARD_ROLE
        ):
            return False
        cached = self._calls.get(id(expression))
        if cached is None:
            context.variables = self._scopes[index]
            mark = len(context.diagnostics)
            text = expression_text(expression, context, expected_type=ValueType.INT)
            del context.diagnostics[mark:]
            cached = self._calls[id(expression)] = not text.startswith("raw_expression ")
        return cached

    def _is_card_value(self, index: int, value: Expression, cards: set[CardKey]) -> bool:
        source = self._variable(index, value)
        return (
            is_int_literal(value)
            or (source is not None and source in cards)
            or self._is_card_call(index, value)
        )

    def _visit(self, index: int, node: Expression | GuiAction) -> None:
        pending: list[Expression | GuiAction] = [node]
        while pending:
            item = pending.pop()
            parameters = item.action.parameters if isinstance(item, GuiAction) else item.parameters
            if isinstance(item, GuiAction):
                pending.extend(item.children)
                if item.action.id in {ACTION_SETVAR, ACTION_FORLOOP} and len(parameters) >= 2:
                    target = self._variable(index, parameters[0])
                    if target is not None:
                        self._writes.setdefault(target, []).append((index, parameters[1]))
            raw = item.action.raw_reference if isinstance(item, GuiAction) else item.raw_reference
            if not raw:
                self._record_uses(index, item, parameters)
            pending.extend(parameters)

    def _record_uses(
        self, index: int, item: Expression | GuiAction, parameters: tuple[Expression, ...]
    ) -> None:
        for child, kind in _source_positions(item, self._context):
            found = self._variable(index, child)
            if found is not None and kind is CARD:
                self._used[found] = self._used.get(found, 0) + 1
        if (
            isinstance(item, Expression)
            and len(parameters) == 2
            and (operator := operator_text(item, self._context)) is not None
            and operator[0].token in {"==", "!="}
            and operator[0].parameter_types == (ValueType.INT, ValueType.INT)
        ):
            for child, other in (
                (parameters[0], parameters[1]),
                (parameters[1], parameters[0]),
            ):
                found = self._variable(index, child)
                if found is not None and self._is_card_call(index, other):
                    self._used[found] = self._used.get(found, 0) + 1
