"""Help and exact fixes for common mistakes from other languages."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source
from tests.support.source import apply_fix, multiline_module


def _diagnostics(body: str):
    return validate_source(multiline_module(body), filename="x.aa2m").diagnostics


# body, diagnostic code, help substring, fix replacements
SYNTAX_HINTS = [
    ("if y = 3 { }", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("break if y = 1;", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("let q: bool = y = 1;", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("y /= 2;", "SYNTAX_ERROR", "aa2m has no `/=`", ["y = y / 2"]),
    ("y += 1 + 2;", "SYNTAX_ERROR", "aa2m has no `+=`", ["y = y + (1 + 2)"]),
    ("y++;", "SYNTAX_ERROR", "aa2m has no `++`", ["y = y + 1"]),
    ("y--;", "SYNTAX_ERROR", "aa2m has no `--`", ["y = y - 1"]),
    ("if y > 1 and y < 3 { }", "SYNTAX_ERROR", "use `&&`", ["&&"]),
    ("if y > 1 or y < 3 { }", "SYNTAX_ERROR", "use `||`", ["||"]),
    ("if not y { }", "SYNTAX_ERROR", "use `!` for negation", []),
    ("if y == 1 { } elif y == 2 { }", "SYNTAX_ERROR", "write `else if condition", ["else if"]),
    (
        "if y == 1 { }\n    elseif y == 2 { }",
        "SYNTAX_ERROR",
        "write `else if condition",
        ["else if"],
    ),
    ("if y == 1 { } elif (y == 2) { }", "UNKNOWN_ACTION_NAME", "write `else if condition", []),
    ("let z = 1;", "SYNTAX_ERROR", "declarations need a type", []),
    ("WriteLog('hi');", "SYNTAX_ERROR", 'strings use double quotes: "text"', ['"hi"']),
    ("return;", "SYNTAX_ERROR", "aa2m has no `return`", []),
    ("function f() {}", "SYNTAX_ERROR", "define a `macro`", []),
    ("switch y {}", "SYNTAX_ERROR", "aa2m has no `switch`", []),
    ("while y < 3 { y = y + 1; }", "SYNTAX_ERROR", "aa2m has no `while`", []),
    (
        "while (y < 3) { y = y + 1; }",
        "UNKNOWN_ACTION_NAME",
        "aa2m has no `while`",
        ["loop { break if !(y < 3);"],
    ),
    ("/* open", "SYNTAX_ERROR", "never closed with `*/`", []),
]


@pytest.mark.parametrize(
    ("body", "code", "help", "replacements"), SYNTAX_HINTS, ids=[item[0] for item in SYNTAX_HINTS]
)
def test_hint_help_and_fixes(body, code, help, replacements):
    source = multiline_module(body)
    first = validate_source(source, filename="x.aa2m").diagnostics[0]

    assert first.code == code
    assert first.help is not None
    assert help in first.help
    assert [fix.replacement for fix in first.fixes] == replacements
    if replacements:
        fixed = apply_fix(source, first.fixes[0])
        assert validate_source(fixed, filename="x.aa2m").errors == ()


def test_elseif_call_form_is_a_reserved_name():
    first = _diagnostics("if y == 1 { } elseif (y == 2) { }")[0]

    assert first.message == "invalid source name 'elseif'"
    assert "write `else if condition" in first.help
    assert first.fixes == ()


def test_quote_fix_replaces_the_whole_literal():
    source = multiline_module("WriteLog('hi');")
    (fix,) = validate_source(source, filename="x.aa2m").diagnostics[0].fixes

    assert apply_fix(source, fix) == multiline_module('WriteLog("hi");')


def test_while_fix_rewrites_the_header_keeping_indentation():
    source = multiline_module("while (y < 3) {\n      y = y + 1;\n    }")
    (fix,) = validate_source(source, filename="x.aa2m").diagnostics[0].fixes

    assert fix.replacement == "loop {\n      break if !(y < 3);"
    assert (fix.span.start_line, fix.span.start_column) == (5, 5)
    assert fix.span.end_line == 5
    assert apply_fix(source, fix) == multiline_module(
        "loop {\n      break if !(y < 3);\n      y = y + 1;\n    }"
    )


@pytest.mark.parametrize(
    "body",
    [
        "while (y < 3) {\n      y = y + 1;\n      y = y + 2;\n    }",
        "while (y < 3) {\n    }",
        "while (y < 3) { y = y + 1; }",
    ],
    ids=["multi-line-body", "empty-multi-line", "single-line"],
)
def test_while_fix_compiles_cleanly_for_each_layout(body):
    source = multiline_module(body)
    first = validate_source(source, filename="x.aa2m").errors[0]

    assert validate_source(apply_fix(source, first.fixes[0]), filename="x.aa2m").errors == ()


def test_applying_each_fix_in_turn_clears_several_errors():
    source = multiline_module("y += 1;\n    y *= 2 + 3;\n")
    for _ in range(2):
        errors = validate_source(source, filename="x.aa2m").errors
        assert errors[0].fixes
        source = apply_fix(source, errors[0].fixes[0])
    assert validate_source(source, filename="x.aa2m").errors == ()


def test_a_user_macro_named_while_still_works():
    source = (
        'macro "while" { param "c" int; WriteLog("x"); }\n'
        'module "m" { trigger "t" { on CARD_ADDED; while(1); } }\n'
    )

    result = validate_source(source, filename="x.aa2m")

    assert result.diagnostics == ()
