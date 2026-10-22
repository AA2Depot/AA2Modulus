"""Lower a bound module to a SIR module."""

from __future__ import annotations

from ..context.limits import SourceLimits, resolve_source_limits
from ..context.operation import SourceContext
from ..hir.limits import check_bound_hir
from ..hir.nodes import (
    BoundModule,
    BoundTrigger,
)
from ..language.types import wire_type
from ..metadata.snapshot import MetadataSnapshot
from ..model.records import GlobalVariable, Module, Trigger, Variable
from .actions import lower_actions, lower_event
from .expressions import lower_expression


def _trigger(node: BoundTrigger) -> Trigger:
    return Trigger(
        node.name,
        tuple(lower_event(item) for item in node.events),
        tuple(
            Variable(
                wire_type(item.type),
                item.name,
                lower_expression(item.default),
                source_span=item.source_span,
            )
            for item in node.locals
        ),
        lower_actions(node.statements),
        source_span=node.source_span,
    )


def lower_bound_module(
    module: BoundModule,
    *,
    metadata: MetadataSnapshot | None = None,
    context: SourceContext | None = None,
    source_limits: SourceLimits | None = None,
) -> Module:
    """Lower Bound HIR; annotate only with an explicitly supplied catalog.

    Binding has already selected the source policy. Pure lowering preserves
    those selections and does not read any default metadata or policy files.
    """

    if context is not None:
        if metadata is not None and metadata is not context.metadata:
            raise ValueError("metadata conflicts with the supplied SourceContext")
        metadata = context.metadata
        context = SourceContext.resolve(context, source_limits=source_limits)
        source_limits = context.source_limits

    check_bound_hir(
        module,
        filename=context.filename if context is not None else "<source>",
        limits=resolve_source_limits(source_limits),
    )

    result = Module(
        module.name,
        module.description,
        tuple(_trigger(item) for item in module.triggers),
        tuple(
            GlobalVariable(
                wire_type(item.type),
                item.name,
                item.default.value,
                item.current.value,
                item.initialized,
                source_span=item.source_span,
            )
            for item in module.globals
        ),
        module.dependencies,
        source_span=module.source_span,
    )
    return result if metadata is None else metadata.resolve_module(result)
