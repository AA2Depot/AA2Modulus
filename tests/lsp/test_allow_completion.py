"""Completion inside ``@allow(`` offers the acknowledgeable native hazards."""

from __future__ import annotations

import pytest
from lsprotocol.types import CompletionItemKind

from aa2modulus.lsp.completion.dispatch import completions

PERMITTED = {
    "REVIEWED_VALUE_TYPE_MISMATCH",
    "NATIVE_DEFECTIVE_EXPRESSION",
    "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH",
}
HEAD = 'module "M" { trigger "T" { on PC_RESPONSE;\n  '


def _items(text, context):
    return completions(text, len(text), context)


def test_all_permitted_codes_are_offered_as_enum_members(context):
    items = _items(HEAD + "@allow(", context)
    assert {item.label for item in items} == PERMITTED
    assert {item.kind for item in items} == {CompletionItemKind.EnumMember}


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("REV", {"REVIEWED_VALUE_TYPE_MISMATCH"}),
        ("NATIVE_", {"NATIVE_DEFECTIVE_EXPRESSION"}),
        ("EXPRESSION_METADATA", {"EXPRESSION_METADATA_RETURN_TYPE_MISMATCH"}),
        ("ZZZ", set()),
    ],
)
def test_typed_prefix_filters_the_codes(context, typed, expected):
    assert {item.label for item in _items(HEAD + "@allow(" + typed, context)} == expected


def test_codes_already_listed_in_the_attribute_are_excluded(context):
    text = HEAD + "@allow(REVIEWED_VALUE_TYPE_MISMATCH, "
    assert {item.label for item in _items(text, context)} == PERMITTED - {
        "REVIEWED_VALUE_TYPE_MISMATCH"
    }


def test_codes_listed_in_an_earlier_attribute_are_still_offered(context):
    text = HEAD + "@allow(REVIEWED_VALUE_TYPE_MISMATCH)\n  @allow("
    assert {item.label for item in _items(text, context)} == PERMITTED


def test_statement_completion_after_an_attribute_is_unaffected(context):
    labels = {
        item.label for item in _items(HEAD + "@allow(NATIVE_DEFECTIVE_EXPRESSION)\n  ", context)
    }
    assert {"if", "let", "loop"} <= labels
    assert not labels & PERMITTED


def test_ordinary_statement_completion_offers_no_hazard_codes(context):
    labels = {item.label for item in _items(HEAD, context)}
    assert {"if", "let"} <= labels
    assert not labels & PERMITTED
