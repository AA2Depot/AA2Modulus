"""Literal values, type checks and card typing rules."""

from __future__ import annotations

import math
from typing import NoReturn

from ...core.source_names import is_qualified_source_name
from ...hir.nodes import (
    BoundExpression,
    BoundLiteral,
)
from ...language.types import (
    CARD,
    SourceType,
    source_type_name,
    widens_to,
)
from ...model.types import INT32_RANGE, ModelError, TypeId, ValueType
from ...model.values import Value
from ...syntax.ast import (
    FloatBitsLiteral,
    SourceBinary,
    SourceConstantReference,
    SourceExpression,
    SourceGroup,
    SourceLiteral,
    SourceLiteralValue,
    SourceName,
)
from .reporting import node_span, raise_error
from .rewrites import card_fixes
from .state import BindContext

# The value a formal of each scalar type takes while its definition is validated.
SCALAR_DEFAULTS: dict[TypeId, SourceLiteralValue] = {
    ValueType.INT: 0,
    ValueType.BOOL: False,
    ValueType.FLOAT: 0.0,
    ValueType.STRING: "",
}


def literal_value(context: BindContext, node: SourceLiteral) -> Value:
    value = node.value
    if value is None:
        return Value.invalid(source_span=node_span(node))
    if isinstance(value, bool):
        return Value.boolean(value, source_span=node_span(node))
    if isinstance(value, int):
        if value not in INT32_RANGE:
            raise_error(
                context,
                node,
                "INT_OUT_OF_RANGE",
                "int literal is outside the int32 range (-2147483648 to 2147483647)",
            )
        return Value.integer(value, source_span=node_span(node))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise_error(
                context,
                node,
                "FLOAT_OUT_OF_RANGE",
                "decimal float is outside the finite binary32 range",
            )
        try:
            return Value.floating(value, source_span=node_span(node))
        except ModelError as exc:
            raise_error(context, node, "FLOAT_OUT_OF_RANGE", str(exc))
    if isinstance(value, str):
        return Value.string(value, source_span=node_span(node))
    if isinstance(value, FloatBitsLiteral):
        return Value.floating_bits(value.bits, source_span=node_span(node))
    raise_error(context, node, "INVALID_LITERAL", f"unsupported literal value {value!r}")


def check_type(
    context: BindContext, actual: SourceType, expected: SourceType | None, node: object
) -> None:
    if expected is not None and not widens_to(actual, expected):
        raise_error(
            context,
            node,
            "SOURCE_TYPE_MISMATCH",
            f"expected {source_type_name(expected)}, found {source_type_name(actual)}",
        )


def _ungrouped(node: SourceExpression) -> SourceExpression:
    while isinstance(node, SourceGroup):
        node = node.expression
    return node


def literal_like(node: SourceExpression, bound: BoundExpression) -> bool:
    """An int literal or constant, which is accepted as a card (seat number)."""

    syntax = _ungrouped(node)
    return (
        isinstance(bound, BoundLiteral)
        and bound.type == ValueType.INT
        and (
            isinstance(syntax, (SourceLiteral, SourceConstantReference))
            or (isinstance(syntax, SourceName) and not is_qualified_source_name(syntax.name))
        )
    )


def card_mismatch(context: BindContext, node: SourceExpression) -> NoReturn:
    raise_error(
        context,
        node,
        "SOURCE_TYPE_MISMATCH",
        "expected card, found int",
        help=(
            "this expression has source type int; declare seat variables as card, "
            "or write Card(...) to convert it explicitly"
        ),
        fixes=card_fixes(node),
    )


def check_card_comparison(
    context: BindContext, node: SourceBinary, left: BoundExpression, right: BoundExpression
) -> None:
    """``card == int`` compares a seat with a number: the int side must be a card."""

    for side, bound, other in ((node.left, left, right), (node.right, right, left)):
        if other.type is CARD and bound.type == ValueType.INT and not literal_like(side, bound):
            card_mismatch(context, side)
