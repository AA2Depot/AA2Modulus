"""Diagnostic wording: source vocabulary, plain types, readable syntax errors, help text."""

from __future__ import annotations

import re

import pytest

from aa2modulus.app.compile import validate_source
from aa2modulus.syntax.parser.errors import SourceParseError
from aa2modulus.syntax.parser.units import parse_source_ast
from aa2modulus.validation.validator.module import validate_module
from tests.support.source import parse_module


def _module(body: str) -> str:
    return f'module "M" {{ trigger "T" {{ on CARD_ADDED; {body} }} }}'


def _first_error(source: str):
    return validate_source(source).errors[0]


def test_binding_type_mismatch_names_source_types():
    diagnostic = _first_error(_module("let a: int = true;"))
    assert diagnostic.code == "SOURCE_TYPE_MISMATCH"
    assert diagnostic.message == "expected int, found bool"


def test_missing_terminator_points_after_the_previous_statement():
    source = (
        'module "M" {\n  trigger "T" {\n    on CARD_ADDED;\n    let a: int = 1\n    let b: int = '
        "2;\n  }\n}"
    )
    with pytest.raises(SourceParseError) as raised:
        parse_source_ast(source, filename="f.aa2m")
    error = raised.value
    assert error.message == "expected `;`, found `let`"
    assert (error.line, error.column) == (4, 19)
    assert error.source_span is not None
    assert (error.source_span.start_line, error.source_span.start_column) == (4, 19)
    assert str(error) == "f.aa2m:4:19: error[SYNTAX_ERROR]: expected `;`, found `let`"


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ('module "M" {', "expected `}`, found end of file"),
        (
            'module "M" { trigger "T" { SetVariable(,); } }',
            "expected an expression or `)`, found `,`",
        ),
        ('module "M" { trigger "T" { on ; } }', "expected a name, found `;`"),
        ('module "M" { trigger "T" { @ } }', "unexpected character `@`"),
        ('module "M" { trigger "T" { let a: string = "abc; } }', "unterminated string literal"),
        (
            'module "M" { } x',
            "expected `import`, `trigger`, `macro`, `const`, or `module`, found `x`",
        ),
    ],
)
def test_syntax_errors_use_readable_tokens(source, message):
    with pytest.raises(SourceParseError) as raised:
        parse_source_ast(source)
    assert raised.value.message == message
    assert "Token(" not in raised.value.message
    assert not re.search(r"line \d+", raised.value.message)


@pytest.mark.parametrize(
    ("event", "expression", "message"),
    [
        pytest.param(
            "NPC_AFTER_RESPONSE",
            "Context.NpcCurrentResponse",
            "Context.NpcCurrentResponse only reads an int from event data during "
            "NPC_RESPONSE; during NPC_AFTER_RESPONSE AAUnlimited returns `false` instead "
            "of an int, so this reads unspecified bits that can change between reads",
            id="int101-literal-fallback",
        ),
        pytest.param(
            "PC_RESPONSE",
            "Context.NpcOriginalResponse",
            "Context.NpcOriginalResponse only reads an int from event data during "
            "NPC_RESPONSE; during PC_RESPONSE AAUnlimited returns `false` instead "
            "of an int, so this reads unspecified bits that can change between reads",
            id="int100-literal-fallback",
        ),
        pytest.param(
            "PC_RESPONSE",
            "Conversation.IsAnswering",
            "during PC_RESPONSE, Conversation.IsAnswering returns a bool field instead "
            "of an int, so this reads unspecified bits that can change between reads",
            id="int70-bool-field",
        ),
    ],
)
def test_reviewed_callback_mismatch_says_what_the_event_returns(event, expression, message):
    source = _module(f"let a: int = {expression};").replace("CARD_ADDED", event)
    diagnostic = next(
        item
        for item in validate_source(source).errors
        if item.code == "REVIEWED_VALUE_TYPE_MISMATCH"
    )
    assert diagnostic.message == message
    assert diagnostic.notes == ('in trigger "T"',)
    assert diagnostic.help is None
    for internal in ("Thread::", "Value", "encoded", "event 14", "this module reads"):
        assert internal not in diagnostic.message


def test_reviewed_callback_unknown_context_names_the_value_events():
    source = 'module "M" { trigger "T" { let a: int = Conversation.IsAnswering; } }'
    (warning,) = [
        item
        for item in validate_source(source).warnings
        if item.code == "REVIEWED_VALUE_CONTEXT_UNKNOWN"
    ]
    assert warning.message == (
        "Conversation.IsAnswering only reads an int from event data during "
        "PC_CONVERSATION_STATE_UPDATED or PC_CONVERSATION_LINE_UPDATED, but this trigger "
        "has no fully known event, so its runtime type is unknown"
    )


def test_native_resave_warning_has_no_wire_identity_text():
    source = _module("let a: int = Context.NpcOriginalResponse;").replace(
        "CARD_ADDED", "PC_RESPONSE"
    )
    result = validate_module(parse_module(source), profile="native")
    (resave,) = [i for i in result.diagnostics if i.code == "NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE"]
    assert "is an int here, but AAUnlimited saves it as a bool" in resave.message
    assert "expression/" not in resave.message


def test_rewrite_hint_lands_in_help_not_message():
    diagnostic = _first_error(_module("End();"))
    assert diagnostic.code == "UNKNOWN_ACTION_NAME"
    assert "use" not in diagnostic.message
    assert diagnostic.help == "use 'StopThread'"
