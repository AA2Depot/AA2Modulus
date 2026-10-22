"""Transformer rules: Macros, triggers, trigger templates and imports, events and locals."""

from __future__ import annotations

from lark import Token, v_args
from lark.tree import Meta

from ....core.locations import SourceSpan
from ...ast import (
    SourceEvent,
    SourceLocal,
    SourceMacro,
    SourceParameter,
    SourceSlotBinding,
    SourceStatement,
    SourceTrigger,
    SourceTriggerImport,
    SourceTriggerTemplate,
)
from ..spans import meta_span, token_span
from .base import (
    TransformerBase,
    as_expression,
    as_expressions,
    as_named,
    as_source_type,
    as_statement,
    as_token,
)


@v_args(meta=True)
class DefinitionsMixin(TransformerBase):
    def macro_parameter(self, meta: Meta, children: list[object]) -> SourceParameter:
        name = as_named(children[0])
        return SourceParameter(
            name.value,
            as_source_type(children[1]),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
            quoted_name=name.quoted,
        )

    def template_slot(self, meta: Meta, children: list[object]) -> SourceParameter:
        name = as_named(children[0])
        return SourceParameter(
            name.value,
            as_source_type(children[1]),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
            quoted_name=name.quoted,
        )

    def macro_definition(self, meta: Meta, children: list[object]) -> SourceMacro:
        name = as_named(children[0])
        parameters: list[SourceParameter] = []
        body: list[SourceStatement] = []
        for child in children[1:]:
            if isinstance(child, SourceParameter):
                parameters.append(child)
            else:
                body.append(as_statement(child))
        return SourceMacro(
            name.value,
            tuple(parameters),
            tuple(body),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
        )

    def trigger(self, meta: Meta, children: list[object]) -> SourceTrigger:
        name_token = as_token(children[0])
        events: list[SourceEvent] = []
        locals_: list[SourceLocal] = []
        statements: list[SourceStatement] = []
        for child in children[1:]:
            if isinstance(child, SourceEvent):
                events.append(child)
            elif isinstance(child, SourceLocal):
                locals_.append(child)
            else:
                statements.append(as_statement(child))
        return SourceTrigger(
            self._string(name_token),
            tuple(events),
            tuple(locals_),
            tuple(statements),
            source_span=meta_span(meta, self.filename),
            name_span=token_span(name_token, self.filename),
        )

    def trigger_template(self, meta: Meta, children: list[object]) -> SourceTriggerTemplate:
        name_token = as_token(children[0])
        name = self._string(name_token)
        slots: list[SourceParameter] = []
        events: list[SourceEvent] = []
        locals_: list[SourceLocal] = []
        statements: list[SourceStatement] = []
        for child in children[1:]:
            if isinstance(child, SourceParameter):
                slots.append(child)
            elif isinstance(child, SourceEvent):
                events.append(child)
            elif isinstance(child, SourceLocal):
                locals_.append(child)
            else:
                statements.append(as_statement(child))
        span = meta_span(meta, self.filename)
        trigger = SourceTrigger(
            name,
            tuple(events),
            tuple(locals_),
            tuple(statements),
            source_span=span,
            name_span=token_span(name_token, self.filename),
        )
        return SourceTriggerTemplate(trigger, tuple(slots), source_span=span)

    def trigger_import(self, meta: Meta, children: list[object]) -> SourceTriggerImport:
        template_token = as_token(children[0])
        template = self._string(template_token)
        rename: str | None = None
        rename_span: SourceSpan | None = None
        slots: list[SourceSlotBinding] = []
        for child in children[1:]:
            if isinstance(child, SourceSlotBinding):
                slots.append(child)
            elif isinstance(child, Token):
                rename = self._string(child)
                rename_span = token_span(child, self.filename)
            else:
                raise TypeError(f"unexpected trigger import item {child!r}")
        return SourceTriggerImport(
            template,
            rename,
            tuple(slots),
            source_span=meta_span(meta, self.filename),
            template_span=token_span(template_token, self.filename),
            name_span=rename_span,
        )

    def slot_binding(self, meta: Meta, children: list[object]) -> SourceSlotBinding:
        name = as_named(children[0])
        return SourceSlotBinding(
            name.value,
            as_expression(children[1]),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
        )

    def named_event_empty(self, meta: Meta, children: list[object]) -> SourceEvent:
        name = as_named(children[0])
        return SourceEvent(
            name=name.value, source_span=meta_span(meta, self.filename), name_span=name.span
        )

    def named_event_args(self, meta: Meta, children: list[object]) -> SourceEvent:
        name = as_named(children[0])
        return SourceEvent(
            name=name.value,
            arguments=as_expressions(children[1]) if len(children) > 1 else (),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
        )

    def raw_event_empty(self, meta: Meta, children: list[object]) -> SourceEvent:
        return SourceEvent(
            identifier=self._int(as_token(children[0])), source_span=meta_span(meta, self.filename)
        )

    def raw_event_args(self, meta: Meta, children: list[object]) -> SourceEvent:
        return SourceEvent(
            identifier=self._int(as_token(children[0])),
            arguments=as_expressions(children[1]) if len(children) > 1 else (),
            source_span=meta_span(meta, self.filename),
        )

    def local_decl(self, meta: Meta, children: list[object]) -> SourceLocal:
        name = as_named(children[0])
        return SourceLocal(
            name.value,
            as_source_type(children[1]),
            as_expression(children[2]),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
            quoted_name=name.quoted,
        )
