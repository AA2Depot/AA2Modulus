"""Typed node coercions and the transformer base shared by the grammar-area mixins."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import NoReturn

from lark import Token, Transformer_NonRecursive
from lark.tree import Meta

from ....core.locations import SourceSpan
from ....language.types import CARD, SourceType
from ....model.types import TypeId
from ...ast import (
    SourceAction,
    SourceAllow,
    SourceAssignment,
    SourceBinary,
    SourceCall,
    SourceCardConversion,
    SourceConstantReference,
    SourceElse,
    SourceElseIf,
    SourceExpression,
    SourceFor,
    SourceGroup,
    SourceIf,
    SourceLiteral,
    SourceLoop,
    SourceLoopControl,
    SourceMemberAction,
    SourceMemberCall,
    SourceMemberProperty,
    SourceName,
    SourceRawConstant,
    SourceRawExpression,
    SourceRawExpressionPayload,
    SourceRawNamedConstant,
    SourceRawParameters,
    SourceRawVariable,
    SourceStatement,
    SourceUnary,
    SourceVariableReference,
)
from ...spans import qualified_segment_spans
from ..errors import SourceParseError
from ..spans import meta_span, token_span


@dataclass(frozen=True, slots=True)
class Description:
    value: str


@dataclass(frozen=True, slots=True)
class Dependency:
    value: str


@dataclass(frozen=True, slots=True)
class AllowAttribute:
    codes: tuple[str, ...]
    code_spans: tuple[SourceSpan, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class NamedValue:
    value: str
    span: SourceSpan
    explicit_variable: bool = False
    quoted: bool = False


def as_named(value: object) -> NamedValue:
    if isinstance(value, NamedValue):
        return value
    raise TypeError(f"expected source name with span, got {value!r}")


def as_type_id(value: object) -> TypeId:
    if not isinstance(value, bool) and isinstance(value, int):
        return value
    raise TypeError(f"unexpected source type {value!r}")


def as_source_type(value: object) -> SourceType:
    return CARD if value is CARD else as_type_id(value)


def as_token(value: object) -> Token:
    if isinstance(value, Token):
        return value
    raise TypeError(f"expected source token, got {value!r}")


def as_expression(value: object) -> SourceExpression:
    if isinstance(
        value,
        (
            SourceLiteral,
            SourceName,
            SourceCall,
            SourceMemberCall,
            SourceMemberProperty,
            SourceUnary,
            SourceBinary,
            SourceGroup,
            SourceCardConversion,
            SourceVariableReference,
            SourceConstantReference,
            SourceRawExpression,
        ),
    ):
        return value
    raise TypeError(f"expected source expression, got {value!r}")


def as_expressions(value: object) -> tuple[SourceExpression, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"expected source expression tuple, got {value!r}")
    return tuple(as_expression(item) for item in value)


def as_statement(value: object) -> SourceStatement:
    if isinstance(
        value,
        (
            SourceAction,
            SourceMemberAction,
            SourceAssignment,
            SourceElseIf,
            SourceElse,
            SourceIf,
            SourceLoop,
            SourceFor,
            SourceLoopControl,
        ),
    ):
        return value
    raise TypeError(f"expected source statement, got {value!r}")


@dataclass(frozen=True, slots=True)
class Block:
    statements: tuple[SourceStatement, ...]
    span: SourceSpan


def as_statements(value: object) -> tuple[SourceStatement, ...]:
    if isinstance(value, Block):
        return value.statements
    if not isinstance(value, tuple):
        raise TypeError(f"expected source statement tuple, got {value!r}")
    return tuple(as_statement(item) for item in value)


def as_literal(value: object) -> SourceLiteral:
    if isinstance(value, SourceLiteral):
        return value
    raise TypeError(f"expected source literal, got {value!r}")


def as_const_value(value: object) -> SourceLiteral | SourceName | SourceConstantReference:
    if isinstance(value, (SourceLiteral, SourceName, SourceConstantReference)):
        return value
    raise TypeError(f"expected constant value, got {value!r}")


def as_payload(value: object) -> SourceRawExpressionPayload:
    if isinstance(
        value, (SourceRawConstant, SourceRawVariable, SourceRawNamedConstant, SourceRawParameters)
    ):
        return value
    raise TypeError(f"expected raw expression payload, got {value!r}")


def fold_binary(children: list[object], filename: str, meta: Meta) -> SourceExpression:
    result = as_expression(children[0])
    for index in range(1, len(children), 2):
        result = SourceBinary(
            str(children[index]),
            result,
            as_expression(children[index + 1]),
            source_span=meta_span(meta, filename),
        )
    return result


def join_spans(start: SourceExpression, end: SourceSpan) -> SourceSpan | None:
    """Span from the start of ``start`` to the end of ``end``."""

    begin = getattr(start, "source_span", None)
    if not isinstance(begin, SourceSpan):
        return None
    return SourceSpan(
        begin.filename, begin.start_line, begin.start_column, end.end_line, end.end_column
    )


class TransformerBase(Transformer_NonRecursive[Token, object]):
    """Shared state and token helpers of every grammar-area mixin."""

    def __init__(self, filename: str) -> None:
        super().__init__()
        self.filename = filename
        self.allows: list[SourceAllow] = []

    def _fail(
        self,
        meta: Meta | Token,
        message: str,
        code: str = "SYNTAX_ERROR",
        *,
        help: str | None = None,
    ) -> NoReturn:
        span = (
            token_span(meta, self.filename)
            if isinstance(meta, Token)
            else meta_span(meta, self.filename)
        )
        raise SourceParseError(
            self.filename,
            getattr(meta, "line", 1),
            getattr(meta, "column", 1),
            message,
            code,
            source_span=span,
            help=help,
        )

    def _string(self, token: Token) -> str:
        try:
            decoded = json.loads(str(token))
        except json.JSONDecodeError as exc:
            self._fail(token, f"invalid JSON string: {exc.msg}", "INVALID_STRING")
        if isinstance(decoded, str):
            return decoded
        raise TypeError(f"JSON string token decoded to non-string value {decoded!r}")

    def _int(self, token: Token) -> int:
        try:
            return int(str(token))
        except ValueError as exc:
            self._fail(token, str(exc), "INVALID_NUMBER")

    def _identifier(self, token: Token) -> str:
        if str(token) == "const" or str(token).casefold() == "card":
            self._fail(token, f"{str(token)!r} is a reserved keyword")
        return str(token)

    def _member_chain(
        self, receiver: SourceExpression, token: Token
    ) -> tuple[SourceExpression, str, SourceSpan]:
        """Split a lexed member token; leading segments of ``a.b.c`` become property reads.

        The lexer joins ``a.b`` into one qualified-name token, so ``receiver.a.b``
        arrives as one member token whose leading segments are properties.
        """

        name = str(token)
        parts = name.split(".")
        spans = qualified_segment_spans(name, token_span(token, self.filename))
        for part, span in zip(parts[:-1], spans[:-1], strict=True):
            assert span is not None
            receiver = SourceMemberProperty(
                receiver, part, source_span=join_spans(receiver, span), name_span=span
            )
        last = spans[-1]
        assert last is not None
        return receiver, parts[-1], last
