"""Independent editor regressions for the metadata/callable catalog plan.

Expected IDs and value data below are pinned compatibility facts. These tests
intentionally do not derive their expected answer from the catalog being tested.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from lsprotocol.types import CompletionItemKind

from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.signature.help import signature_help
from aa2modulus.model.types import ValueType
from aa2modulus.pipeline.analysis import analyze_source
from tests.support.lsp_workspace import apply_text_edit


def _selected_reference(analysis, authored_name):
    assert analysis.bound is not None
    return next(
        reference
        for reference in analysis.bound.references
        if reference.name == authored_name and reference.metadata is not None
    )


_KEYPRESS_GETTER_LABELS = {"Context.KeyPress"}
_KEYPRESS_CONSTANT_LABELS = {"Constants.EventType.KEY_PRESS"}


def _completion_references(analysis):
    assert analysis.bound is not None
    return tuple(
        reference for reference in analysis.bound.references if reference.metadata is not None
    )


def _assert_keypress_completions_bind_to(context, kind, labels, expected_class, expected_id):
    source = 'module "M" { trigger "T" { let value: int = ; } }'
    cursor = source.index("=") + 1
    items = [
        item
        for item in completions(source, cursor, context)
        if item.kind == kind and item.label in labels
    ]

    assert items
    for item in items:
        analysis = analyze_source(apply_text_edit(source, item), context=context)
        assert analysis.result.is_valid
        (selected,) = _completion_references(analysis)
        assert type(selected.metadata).__name__ == expected_class
        assert selected.metadata.id == expected_id


def test_keypress_getter_completion_edits_bind_to_getter_int_102(context):
    _assert_keypress_completions_bind_to(
        context,
        CompletionItemKind.Property,
        _KEYPRESS_GETTER_LABELS,
        "ExpressionMetadata",
        102,
    )


def test_keypress_constant_completion_edits_bind_to_named_constant_int_301(context):
    _assert_keypress_completions_bind_to(
        context,
        CompletionItemKind.Constant,
        _KEYPRESS_CONSTANT_LABELS,
        "NamedConstantMetadata",
        301,
    )


def test_opinion70_completion_deduplicates_equivalent_rows(context):
    source = 'module "M" { trigger "T" { let value: int = Constants.Opinion.OPINION_70; } }'
    cursor = source.index("Constants.Opinion.OPINION_70") + len("Constants.Opinion.OPINION_70")
    items = [
        item
        for item in completions(source, cursor, context)
        if item.label == "Constants.Opinion.OPINION_70" and item.kind == CompletionItemKind.Constant
    ]

    assert len(items) == 1


def test_expression_signature_uses_expression_role_when_macro_name_matches(context):
    source = (
        "macro ToInt { param flag bool; } "
        'module "M" { trigger "T" { let number: int = ToInt("3"); } }'
    )
    assert analyze_source(source, context=context).result.is_valid
    cursor = source.index("ToInt(") + len("ToInt(")

    result = signature_help(source, cursor, context)

    assert result is not None
    labels = [signature.label for signature in result.signatures]
    assert "ToInt(value: string)" in labels
    assert "ToInt(flag: bool)" not in labels


def test_statement_signature_keeps_the_matching_macro_role(context):
    source = 'macro WriteLog { param flag bool; } module "M" { trigger "T" { WriteLog(true); } }'
    cursor = source.index("WriteLog(") + len("WriteLog(")

    result = signature_help(source, cursor, context)

    assert result is not None
    assert [signature.label for signature in result.signatures] == ["WriteLog(flag: bool)"]


@pytest.mark.parametrize(
    ("result_type", "selected_parameters", "rejected_parameters"),
    [
        ("int", "min: int, max: int", "min: float, max: float"),
        ("float", "min: float, max: float", "min: int, max: int"),
    ],
)
def test_overloaded_signature_help_filters_by_expected_result(
    context, result_type, selected_parameters, rejected_parameters
):
    # One shared name for Math.RandomInt and Math.RandomFloat isolates signature
    # filtering from naming policy.
    renamed = {(ValueType.INT, 4), (ValueType.FLOAT, 4)}
    source_policy = replace(
        context.source_policy,
        expression_preferred_names=tuple(
            (scope, identifier, "Dice.Roll" if (scope, identifier) in renamed else name)
            for scope, identifier, name in context.source_policy.expression_preferred_names
        ),
    )
    context = replace(context, source_policy=source_policy)
    source = f'module "M" {{ trigger "T" {{ let result: {result_type} = Dice.Roll('

    result = signature_help(source, len(source), context)

    assert result is not None
    labels = [signature.label for signature in result.signatures]
    assert len(labels) == 1
    assert labels[0].endswith(f"({selected_parameters})")
    assert all(not label.endswith(f"({rejected_parameters})") for label in labels)
