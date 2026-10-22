"""Transformer rules: Operators, calls, member forms, names and raw expressions."""

from __future__ import annotations

from lark import v_args
from lark.tree import Meta

from ....model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR
from ...ast import (
    SourceBinary,
    SourceCall,
    SourceCardConversion,
    SourceExpression,
    SourceGroup,
    SourceMemberCall,
    SourceMemberProperty,
    SourceName,
    SourceRawConstant,
    SourceRawExpression,
    SourceRawNamedConstant,
    SourceRawParameters,
    SourceRawVariable,
    SourceUnary,
    SourceVariableReference,
    raw_payload_text,
)
from ..spans import meta_span, token_span
from .base import (
    TransformerBase,
    as_expression,
    as_expressions,
    as_literal,
    as_named,
    as_payload,
    as_token,
    as_type_id,
    fold_binary,
)


@v_args(meta=True)
class ExpressionsMixin(TransformerBase):
    def expr_list(self, meta: Meta, children: list[object]) -> tuple[SourceExpression, ...]:
        return tuple(as_expression(child) for child in children)

    def or_expr(self, meta: Meta, children: list[object]) -> SourceExpression:
        return fold_binary(children, self.filename, meta)

    def and_expr(self, meta: Meta, children: list[object]) -> SourceExpression:
        return fold_binary(children, self.filename, meta)

    def comparison(self, meta: Meta, children: list[object]) -> SourceExpression:
        if len(children) == 1:
            return as_expression(children[0])
        return SourceBinary(
            str(children[1]),
            as_expression(children[0]),
            as_expression(children[2]),
            source_span=meta_span(meta, self.filename),
        )

    def equality(self, meta: Meta, children: list[object]) -> SourceExpression:
        return self.comparison(meta, children)

    def additive(self, meta: Meta, children: list[object]) -> SourceExpression:
        return fold_binary(children, self.filename, meta)

    def multiplicative(self, meta: Meta, children: list[object]) -> SourceExpression:
        return fold_binary(children, self.filename, meta)

    def unary_expr(self, meta: Meta, children: list[object]) -> SourceUnary:
        return SourceUnary(
            str(children[0]), as_expression(children[1]), source_span=meta_span(meta, self.filename)
        )

    def grouped(self, meta: Meta, children: list[object]) -> SourceGroup:
        return SourceGroup(as_expression(children[0]), source_span=meta_span(meta, self.filename))

    def card_conversion(self, meta: Meta, children: list[object]) -> SourceCardConversion:
        return SourceCardConversion(
            as_expression(children[0]), source_span=meta_span(meta, self.filename)
        )

    def variable_ref(self, meta: Meta, children: list[object]) -> SourceVariableReference:
        token = as_token(children[0])
        return SourceVariableReference(
            self._string(token),
            source_span=meta_span(meta, self.filename),
            name_span=token_span(token, self.filename),
        )

    def call_expr(self, meta: Meta, children: list[object]) -> SourceCall:
        name = as_named(children[0])
        return SourceCall(
            name.value,
            as_expressions(children[1]) if len(children) > 1 else (),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
        )

    def member_call(self, meta: Meta, children: list[object]) -> SourceMemberCall:
        receiver, member, member_span = self._member_chain(
            as_expression(children[0]), as_token(children[1])
        )
        return SourceMemberCall(
            receiver,
            member,
            as_expressions(children[2]) if len(children) > 2 else (),
            source_span=meta_span(meta, self.filename),
            name_span=member_span,
        )

    def member_property(self, meta: Meta, children: list[object]) -> SourceMemberProperty:
        receiver, member, member_span = self._member_chain(
            as_expression(children[0]), as_token(children[1])
        )
        return SourceMemberProperty(
            receiver,
            member,
            source_span=meta_span(meta, self.filename),
            name_span=member_span,
        )

    def bare_name(self, meta: Meta, children: list[object]) -> SourceName:
        name = as_named(children[0])
        return SourceName(
            name.value, source_span=meta_span(meta, self.filename), name_span=name.span
        )

    def raw_expression(self, meta: Meta, children: list[object]) -> SourceRawExpression:
        identifier = self._int(as_token(children[1]))
        payload = as_payload(children[2])
        expected_payload = {
            EXPR_CONSTANT: SourceRawConstant,
            EXPR_VAR: SourceRawVariable,
            EXPR_NAMEDCONSTANT: SourceRawNamedConstant,
        }.get(identifier, SourceRawParameters)
        if not isinstance(payload, expected_payload):
            self._fail(
                meta,
                f"raw expression id {identifier} requires {raw_payload_text(expected_payload)}",
                "PAYLOAD_MISMATCH",
            )
        return SourceRawExpression(
            as_type_id(children[0]),
            identifier,
            payload,
            source_span=meta_span(meta, self.filename),
        )

    def raw_constant(self, meta: Meta, children: list[object]) -> SourceRawConstant:
        return SourceRawConstant(as_literal(children[0]))

    def raw_variable(self, meta: Meta, children: list[object]) -> SourceRawVariable:
        token = as_token(children[0])
        return SourceRawVariable(self._string(token), name_span=token_span(token, self.filename))

    def raw_named_constant(self, meta: Meta, children: list[object]) -> SourceRawNamedConstant:
        return SourceRawNamedConstant(as_type_id(children[0]), self._int(as_token(children[1])))

    def raw_parameters(self, meta: Meta, children: list[object]) -> SourceRawParameters:
        return SourceRawParameters(as_expressions(tuple(children)))
