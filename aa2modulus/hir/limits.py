"""Budgets on binding work and on the bound program (HIR)."""

from __future__ import annotations

from dataclasses import dataclass

from ..context.limits import SourceLimits, check_records, limit_error
from ..core.locations import SourceSpan
from . import nodes as hir


@dataclass(slots=True)
class BindingBudget:
    """Shared charge counter for expression binding, including failed trials."""

    limits: SourceLimits
    filename: str
    used: int = 0

    def charge(self, span: SourceSpan | None) -> None:
        if self.used >= self.limits.max_binding_work:
            limit_error(
                self.filename,
                span,
                "SOURCE_BINDING_WORK_LIMIT",
                "source expression binding exceeds the work limit of "
                f"{self.limits.max_binding_work}",
            )
        self.used += 1


HIR_NODES = (
    hir.BoundModule,
    hir.BoundTrigger,
    hir.BoundGlobal,
    hir.BoundLocal,
    hir.BoundEvent,
    hir.BoundRawEvent,
    hir.BoundAction,
    hir.BoundRawAction,
    hir.BoundAssignment,
    hir.BoundElseIf,
    hir.BoundElse,
    hir.BoundIf,
    hir.BoundLoop,
    hir.BoundFor,
    hir.BoundLoopControl,
    hir.BoundLiteral,
    hir.BoundVariable,
    hir.BoundNamedConstant,
    hir.BoundCall,
    hir.BoundUnary,
    hir.BoundBinary,
    hir.BoundCardConversion,
    hir.BoundRawExpression,
    hir.BoundRawConstant,
    hir.BoundRawVariable,
    hir.BoundRawNamedConstant,
    hir.BoundRawParameters,
)
HIR_NESTED_NODES = (
    hir.BoundAction,
    hir.BoundRawAction,
    hir.BoundAssignment,
    hir.BoundElseIf,
    hir.BoundElse,
    hir.BoundIf,
    hir.BoundLoop,
    hir.BoundFor,
    hir.BoundLoopControl,
    hir.BoundLiteral,
    hir.BoundVariable,
    hir.BoundNamedConstant,
    hir.BoundCall,
    hir.BoundUnary,
    hir.BoundBinary,
    hir.BoundCardConversion,
    hir.BoundRawExpression,
)


def check_bound_hir(module: hir.BoundModule, *, filename: str, limits: SourceLimits) -> None:
    check_records(
        module,
        filename=filename,
        limits=limits,
        phase="bound program",
        node_types=HIR_NODES,
        nested_types=HIR_NESTED_NODES,
    )
