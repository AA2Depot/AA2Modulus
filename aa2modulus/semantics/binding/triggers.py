"""Triggers and their locals."""

from __future__ import annotations

from ...hir.nodes import (
    BoundLocal,
    BoundTrigger,
)
from ...syntax.ast import (
    SourceLocal,
    SourceTrigger,
)
from .declarations import check_constant_collision, check_protected_declaration
from .expressions import bind_expression
from .reporting import bind_or_record
from .state import BindContext
from .statements import bind_children, bind_event


def _check_local(context: BindContext, item: SourceLocal) -> None:
    check_protected_declaration(context, item, serialized=True)
    check_constant_collision(context, item.name, item, "local")


def _bind_local(context: BindContext, item: SourceLocal) -> BoundLocal:
    return BoundLocal(
        item.name,
        item.type,
        bind_expression(context, item.default, item.type),
        source_span=item.source_span,
    )


def bind_trigger(context: BindContext, trigger: SourceTrigger) -> BoundTrigger:
    """Bind a complete local vector before events, defaults, and statements.

    Each local, event and statement is its own error boundary; a local whose
    declaration or default fails stays declared with its type.
    """

    for item in trigger.locals:
        bind_or_record(context, _check_local, context, item)
        context.locals.setdefault(item.name, item.type)
        context.local_declarations.setdefault(item.name, item)
    events = tuple(bind_or_record(context, bind_event, context, item) for item in trigger.events)
    locals_ = tuple(bind_or_record(context, _bind_local, context, item) for item in trigger.locals)
    return BoundTrigger(
        trigger.name,
        events=tuple(item for item in events if item is not None),
        locals=tuple(item for item in locals_ if item is not None),
        statements=bind_children(context, trigger.statements),
        source_span=trigger.source_span,
    )
