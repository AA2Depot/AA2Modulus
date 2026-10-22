"""Rendering of card-typed positions: ``Card(...)`` conversions and comparisons."""

from __future__ import annotations

from ...language.types import CARD_ROLE
from ...model.records import Expression
from ...model.types import EXPR_CONSTANT, EXPR_PAYLOAD_MARKERS, EXPR_VAR, ValueType
from .context import (
    FormatContext,
    operator_text,
)


def is_int_literal(expression: Expression) -> bool:
    """A readable int literal, which the binder accepts as a card."""

    return (
        not expression.raw_reference
        and expression.id == EXPR_CONSTANT
        and expression.constant is not None
        and expression.constant.type is ValueType.INT
        and expression.return_type == ValueType.INT
    )


def is_card_text(expression: Expression, text: str, context: FormatContext) -> bool:
    """Whether ``text``, rendered from ``expression``, binds to a source ``card``."""

    if expression.raw_reference or text.startswith("raw_expression "):
        return False
    if expression.return_type != ValueType.INT:
        return False
    if expression.id == EXPR_VAR:
        name = expression.variable_name
        return (
            name is not None
            and name in context.cards
            and context.variables.get(name) == ValueType.INT
        )
    if expression.id in EXPR_PAYLOAD_MARKERS or operator_text(expression, context) is not None:
        return False
    return context.policy.expression_result_role(ValueType.INT, expression.id) == CARD_ROLE


def card_text(expression: Expression, text: str, context: FormatContext) -> str:
    """Write ``text`` for a card position, converting an int with ``Card(...)``."""

    if is_int_literal(expression) or is_card_text(expression, text, context):
        return text
    return f"Card({text})"


def card_comparison(
    operands: tuple[Expression, ...], left: str, right: str, context: FormatContext
) -> tuple[str, str]:
    """``card == int`` must convert the int side, unless it is a literal."""

    left_card = is_card_text(operands[0], left, context)
    right_card = is_card_text(operands[1], right, context)
    if left_card and not right_card:
        right = card_text(operands[1], right, context)
    elif right_card and not left_card:
        left = card_text(operands[0], left, context)
    return left, right
