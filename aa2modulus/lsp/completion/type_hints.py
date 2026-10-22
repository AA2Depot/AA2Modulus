"""Type hints read from the tokens around a cursor."""

from __future__ import annotations

from collections.abc import Mapping

from lark import Token

from ...context.operation import SourceContext
from ...model.types import ValueType
from .tokens import NAME_TOKENS, last_boundary


def token_type(
    tokens: tuple[Token, ...], visible: Mapping[str, int], context: SourceContext
) -> int | None:
    if len(tokens) != 1:
        return None
    token = tokens[0]
    literals = {
        "SIGNED_INT": ValueType.INT,
        "SIGNED_FLOAT": ValueType.FLOAT,
        "BOOLEAN": ValueType.BOOL,
        "ESCAPED_STRING": ValueType.STRING,
    }
    if token.type in literals:
        return literals[token.type]
    if token.type not in NAME_TOKENS:
        return None
    name = str(token)
    if name in visible:
        return visible[name]
    source_value = context.catalog.source_value(name)
    if source_value is not None:
        return source_value.value_type
    expressions = tuple(
        item for item in context.catalog.expression_candidates(name) if not item.parameter_types
    )
    if len(expressions) == 1:
        return expressions[0].return_type
    constants = context.catalog.named_constant_candidates(name)
    return constants[0].value_type if len(constants) == 1 else None


def surrounding_type(tokens: tuple[Token, ...], visible: Mapping[str, int]) -> int | None:
    segment = tokens[last_boundary(tokens) + 1 :]
    # An assignment/local's known type applies through unfinished nested calls.
    for index, token in enumerate(segment):
        if token.type == "COLON" and index + 1 < len(segment):
            type_token = segment[index + 1]
            if type_token.type == "TYPE" and index + 2 < len(segment):
                try:
                    return int(str(segment[index + 2]))
                except ValueError:
                    return None
            known = {
                "INT": ValueType.INT,
                "BOOL": ValueType.BOOL,
                "FLOAT": ValueType.FLOAT,
                "STRING": ValueType.STRING,
            }
            return known.get(type_token.type)
        if token.type == "EQUAL" and index:
            return visible.get(str(segment[index - 1]))
    if any(token.type == "NOT_OP" for token in segment):
        return ValueType.BOOL
    if any(token.type in {"FOR", "FROM", "TO"} for token in segment):
        return ValueType.INT
    return None


def condition_context(tokens: tuple[Token, ...]) -> bool:
    segment = tokens[last_boundary(tokens) + 1 :]
    return any(token.type in {"IF", "STANDALONE_ELSEIF"} for token in segment)
