"""Shared lookups from a source position to the binder's selections."""

from __future__ import annotations

from lsprotocol import types

from ...core.locations import SourceSpan
from ...hir.symbols import BoundReference
from ...syntax import ast
from ..protocol.positions import PositionCodec, position_codec
from ..workspace.documents import Snapshot


def contains(codec: PositionCodec, span: SourceSpan, position: types.Position) -> bool:
    range_ = codec.range(span)
    point = position.line, position.character
    return (
        (range_.start.line, range_.start.character)
        <= point
        < (
            range_.end.line,
            range_.end.character,
        )
    )


def declaration_span(node: object) -> SourceSpan | None:
    if isinstance(node, ast.SourceTriggerTemplate):
        return node.trigger.name_span or node.source_span
    if isinstance(node, ast.SourceTriggerImport):
        return node.name_span or node.template_span or node.source_span
    return getattr(node, "name_span", None) or getattr(node, "source_span", None)


def bound_references(snapshot: Snapshot) -> tuple[BoundReference, ...]:
    """Strict binder selections, or the authoring view's while the source has errors."""

    analysis = snapshot.analysis
    if analysis.bound is not None and analysis.failure is None:
        return analysis.bound.references
    return snapshot.authoring.references


def reference_at(
    snapshot: Snapshot, position: types.Position, encoding: str
) -> BoundReference | None:
    codec = position_codec(snapshot.document.text, encoding=encoding)
    for item in bound_references(snapshot):
        span = item.source_span
        if (
            span is not None
            and span.filename == snapshot.document.filename
            and contains(codec, span, position)
        ):
            return item
    return None
