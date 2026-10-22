"""Transformer rules: Literals and type names."""

from __future__ import annotations

from lark import v_args
from lark.tree import Meta

from ....language.types import CARD, SourceType
from ....model.types import TypeId, ValueType
from ...ast import (
    FloatBitsLiteral,
    SourceLiteral,
)
from ..spans import meta_span
from .base import (
    TransformerBase,
    as_token,
)


@v_args(meta=True)
class LiteralsMixin(TransformerBase):
    def string_literal(self, meta: Meta, children: list[object]) -> SourceLiteral:
        return SourceLiteral(
            self._string(as_token(children[0])),
            source_span=meta_span(meta, self.filename),
        )

    def int_literal(self, meta: Meta, children: list[object]) -> SourceLiteral:
        return SourceLiteral(
            self._int(as_token(children[0])),
            source_span=meta_span(meta, self.filename),
        )

    def float_literal(self, meta: Meta, children: list[object]) -> SourceLiteral:
        value = float(str(children[0]).rstrip("fF"))
        return SourceLiteral(value, source_span=meta_span(meta, self.filename))

    def float_bits_literal(self, meta: Meta, children: list[object]) -> SourceLiteral:
        return SourceLiteral(
            FloatBitsLiteral(int(str(children[0]), 0), source_span=meta_span(meta, self.filename)),
            source_span=meta_span(meta, self.filename),
        )

    def bool_literal(self, meta: Meta, children: list[object]) -> SourceLiteral:
        return SourceLiteral(str(children[0]) == "true", source_span=meta_span(meta, self.filename))

    def invalid_literal(self, meta: Meta, children: list[object]) -> SourceLiteral:
        return SourceLiteral(None, source_span=meta_span(meta, self.filename))

    def type_invalid(self, meta: Meta, children: list[object]) -> TypeId:
        return ValueType.INVALID

    def type_int(self, meta: Meta, children: list[object]) -> TypeId:
        return ValueType.INT

    def type_bool(self, meta: Meta, children: list[object]) -> TypeId:
        return ValueType.BOOL

    def type_float(self, meta: Meta, children: list[object]) -> TypeId:
        return ValueType.FLOAT

    def type_string(self, meta: Meta, children: list[object]) -> TypeId:
        return ValueType.STRING

    def type_card(self, meta: Meta, children: list[object]) -> SourceType:
        return CARD

    def type_numeric(self, meta: Meta, children: list[object]) -> TypeId:
        return self._int(as_token(children[0]))
