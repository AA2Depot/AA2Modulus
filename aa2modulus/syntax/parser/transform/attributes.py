"""Transformer rules: ``@allow`` attributes on definitions, triggers, declarations, statements."""

from __future__ import annotations

from lark import v_args
from lark.tree import Meta

from ....core.locations import SourceSpan
from ...ast import (
    SourceAllow,
)
from ..spans import meta_span, token_span
from .base import (
    AllowAttribute,
    TransformerBase,
    as_token,
)


@v_args(meta=True)
class AttributesMixin(TransformerBase):
    def allow_attr(self, meta: Meta, children: list[object]) -> AllowAttribute:
        tokens = tuple(as_token(child) for child in children)
        return AllowAttribute(
            tuple(str(token) for token in tokens),
            tuple(token_span(token, self.filename) for token in tokens),
            meta_span(meta, self.filename),
        )

    def module_allow_attr(self, meta: Meta, children: list[object]) -> AllowAttribute:
        return self.allow_attr(meta, children)

    def _allowed(self, children: list[object]) -> object:
        """Record each attribute against the item it prefixes and return the item."""

        item = children[-1]
        target = getattr(item, "source_span", None)
        if not isinstance(target, SourceSpan):
            raise TypeError(f"@allow target without a source span: {item!r}")
        for attribute in children[:-1]:
            if not isinstance(attribute, AllowAttribute):
                raise TypeError(f"expected @allow attribute, got {attribute!r}")
            self.allows.append(
                SourceAllow(attribute.codes, attribute.code_spans, attribute.span, target)
            )
        return item

    def allowed_definition(self, meta: Meta, children: list[object]) -> object:
        return self._allowed(children)

    def allowed_trigger(self, meta: Meta, children: list[object]) -> object:
        return self._allowed(children)

    def allowed_declaration(self, meta: Meta, children: list[object]) -> object:
        return self._allowed(children)

    def allowed_statement(self, meta: Meta, children: list[object]) -> object:
        return self._allowed(children)
