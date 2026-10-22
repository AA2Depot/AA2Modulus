"""Spans, located binding errors, failure collection and symbol references."""

from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn

from ...core.diagnostics import Diagnostic, SourceFix
from ...core.locations import SourceSpan
from ...hir.symbols import BoundReference, ResolvedConstant, SelectedMetadata, SourceDeclaration
from ...language.types import (
    SourceType,
    result_type,
)
from ...language.values import MemberForm
from ...model.native import ActionMetadata, ExpressionMetadata
from ...syntax.ast import (
    SourceTriggerImport,
)
from .state import BindContext, Poisoned, SourceBindingError


def node_span(node: object) -> SourceSpan | None:
    value = getattr(node, "source_span", None)
    return value if isinstance(value, SourceSpan) else None


def name_span_of(node: object) -> SourceSpan | None:
    if isinstance(node, SourceTriggerImport):
        value = node.template_span
    else:
        value = getattr(node, "name_span", None) or getattr(node, "target_span", None)
    return value if isinstance(value, SourceSpan) else node_span(node)


def record_reference(
    context: BindContext,
    name: str,
    node: object,
    *,
    declaration: SourceDeclaration | None = None,
    metadata: SelectedMetadata | None = None,
    value_type: SourceType | None = None,
    member_form: MemberForm | None = None,
) -> None:
    context.references.append(
        BoundReference(
            name,
            name_span_of(node),
            declaration=declaration,
            metadata=metadata,
            type=value_type,
            member_form=member_form,
        )
    )


def record_constant_reference(
    references: list[BoundReference], name: str, node: object, target: ResolvedConstant
) -> None:
    """Record a use of a resolved constant, carrying its declaration, type and value."""

    references.append(
        BoundReference(
            name,
            name_span_of(node),
            declaration=target.declaration,
            type=target.type,
            value=target.value,
        )
    )


def record_variable_reference(
    context: BindContext, name: str, node: object, value_type: SourceType
) -> None:
    record_reference(
        context,
        name,
        node,
        declaration=context.variable_declaration(name),
        value_type=value_type,
    )


def raise_error(
    context: BindContext,
    node: object,
    code: str,
    message: str,
    *,
    help: str | None = None,
    fixes: tuple[SourceFix, ...] = (),
) -> NoReturn:
    span = node_span(node)
    raise SourceBindingError(
        Diagnostic(
            span.filename if span is not None else context.filename,
            span.start_line if span is not None else 1,
            span.start_column if span is not None else 1,
            "error",
            code,
            message,
            related=span.related if span is not None else (),
            source_span=span,
            help=help or None,
            fixes=fixes,
        )
    )


def bind_or_record[**P, T](
    context: BindContext, bind: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T | None:
    """Bind one statement or item, recording its error and returning ``None`` on failure."""

    if context.collector is None:
        return bind(*args, **kwargs)
    try:
        return bind(*args, **kwargs)
    except Poisoned:
        context.collector.suppressed += 1
    except SourceBindingError as exc:
        context.collector.record(exc)
    return None


def join_help(*parts: str) -> str | None:
    """Combine non-empty help fragments into one help line."""

    return "; ".join(part for part in parts if part) or None


def record_member_reference(
    context: BindContext,
    member: str,
    member_span: SourceSpan | None,
    target: ActionMetadata | ExpressionMetadata,
    form: MemberForm,
) -> None:
    context.references.append(
        BoundReference(
            member,
            member_span,
            metadata=target,
            type=result_type(context.source_policy, target)
            if isinstance(target, ExpressionMetadata)
            else None,
            member_form=form,
        )
    )
