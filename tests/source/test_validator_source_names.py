"""Diagnostic headlines use source spellings; native GUI labels stay in notes."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source
from aa2modulus.validation.validator.module import validate_module
from tests.support.source import parse_module

# (trigger body, code, headline text, native GUI label or None)
VALIDATOR_MESSAGES = (
    pytest.param(
        "on PC_RESPONSE; let value: int = Context.NpcOriginalResponse;",
        "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH",
        "Context.NpcOriginalResponse is resolved in int scope but declares bool",
        "Npc Original Response",
        id="expression-metadata-return-type",
    ),
    pytest.param(
        "let x: int = raw_expression int 19 { parameters [ ]; };",
        "EXPRESSION_ARITY",
        "Love expects 2 parameters, but found 0",
        "Love Points",
        id="expression-arity",
    ),
    pytest.param(
        "let x: int = raw_expression int 19 { parameters [ true 1 ]; };",
        "EXPRESSION_PARAMETER_TYPE",
        "parameter 1 of Love expects int, found bool",
        "Love Points",
        id="expression-parameter-type",
    ),
    pytest.param(
        "raw_event 6(1);",
        "EVENT_ARITY",
        "CARD_ADDED expects 0 parameters, but found 1",
        "Card Added to Class",
        id="event-arity",
    ),
    pytest.param(
        "raw_action 1(1, 2);",
        "INVALID_ASSIGNMENT_TARGET",
        "assignment target must be a variable, but found a literal",
        None,
        id="assignment-target",
    ),
    pytest.param(
        "raw_action 108;",
        "ACTION_ARITY",
        "Notification expects 2 parameters, but found 0",
        None,
        id="action-arity",
    ),
    pytest.param(
        'let x: int = 0; raw_action 1(variable("x"));',
        "ACTION_ARITY",
        "assignment expects 2 parameters, but found 1",
        "Set Variable",
        id="assignment-arity",
    ),
    pytest.param(
        'let flag: bool = false; raw_action 9(variable("flag"), 0, 1) { }',
        "FOR_LOOP_TARGET_TYPE",
        "`for` loop target 'flag' must have type int, but has type bool",
        None,
        id="for-loop-target-type",
    ),
    pytest.param(
        'let i: int = 0; raw_action 9(variable("i"), true, 1) { }',
        "ACTION_PARAMETER_TYPE",
        "parameter 2 of `for` loop expects int, found bool",
        "For Loop",
        id="for-loop-parameter-type",
    ),
    pytest.param(
        'raw_action 108("text", 1);',
        "ACTION_PARAMETER_TYPE",
        "parameter 2 of Notification expects bool, found int",
        None,
        id="action-parameter-type",
    ),
)


def _source(body: str) -> str:
    return f'module "M" {{ trigger "T" {{ {body} }} }}'


def _find(diagnostics, code, headline):
    matches = [item for item in diagnostics if item.code == code and item.message == headline]
    assert matches, [(item.code, item.message) for item in diagnostics]
    return matches[0]


def _assert_source_headline(diagnostics, code, headline, native):
    diagnostic = _find(diagnostics, code, headline)
    native_notes = [note for note in diagnostic.notes if note.startswith("native name: ")]
    assert native_notes == ([] if native is None else [f"native name: {native!r}"])


@pytest.mark.parametrize(("body", "code", "headline", "native"), VALIDATOR_MESSAGES)
def test_validator_headline_uses_source_name(body, code, headline, native):
    diagnostics = validate_source(_source(body)).diagnostics
    _assert_source_headline(diagnostics, code, headline, native)


@pytest.mark.parametrize(
    ("body", "code", "headline", "native"),
    [item for item in VALIDATOR_MESSAGES if item.id in {"expression-arity", "action-arity"}],
)
def test_validator_without_a_catalog_loads_the_shipped_policy_names(body, code, headline, native):
    diagnostics = validate_module(parse_module(_source(body))).diagnostics
    _assert_source_headline(diagnostics, code, headline, native)


@pytest.mark.parametrize(
    ("body", "code", "headline"),
    [
        (
            "on clothes_changed(1);",
            "EVENT_ARITY",
            "event 'clothes_changed' has the wrong argument count",
        ),
        ("notification();", "ACTION_ARITY", "action 'notification' is missing an argument"),
    ],
)
def test_binder_arity_names_the_written_spelling(body, code, headline):
    result = validate_source(_source(body))
    assert [(item.code, item.message) for item in result.diagnostics] == [(code, headline)]
