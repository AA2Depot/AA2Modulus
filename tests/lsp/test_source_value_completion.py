"""Applied editor completions for source-level constant values."""

from __future__ import annotations

from lsprotocol.types import CompletionItemKind

from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.documentation.builtins import BuiltinDocumentation
from aa2modulus.model.types import ValueType
from aa2modulus.pipeline.analysis import analyze_source
from tests.support.lsp_workspace import apply_text_edit


def test_school_gate_source_value_completion_applies_as_a_typed_literal(context):
    source = 'module "M" { trigger "T" { let room: int = Constants.Room.SCHOOL; } }'
    cursor = source.index("Constants.Room.SCHOOL") + len("Constants.Room.SCHOOL")

    item = next(
        item
        for item in completions(source, cursor, context)
        if item.label == "Constants.Room.SCHOOL_GATES" and item.kind == CompletionItemKind.Constant
    )

    completed = apply_text_edit(source, item)
    analysis = analyze_source(completed, context=context)
    assert analysis.result.is_valid
    assert item.detail == "Constants.Room.SCHOOL_GATES: int = 0"
    assert analysis.bound is not None
    reference = next(
        item
        for item in analysis.bound.references
        if item.name == "Constants.Room.SCHOOL_GATES" and item.metadata is not None
    )
    assert type(reference.metadata).__name__ == "SourceValue"
    assert reference.metadata.value_type == ValueType.INT
    assert reference.metadata.value.value == 0


def test_source_value_documentation_uses_its_original_constant_row(context):
    source_value = context.catalog.source_value("Constants.Room.SCHOOL_GATES")
    assert source_value is not None
    documentation = BuiltinDocumentation(context.metadata, enabled=True)

    location = documentation.location(source_value)
    assert location is not None
    assert location.uri == f"aa2m-builtin:/{source_value.documentation_key}.md"
    assert location.range.start.line == 0
