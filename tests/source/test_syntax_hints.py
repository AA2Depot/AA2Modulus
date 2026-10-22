"""Help and exact fixes for common mistakes from other languages."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source


def _wrap(body: str) -> str:
    return (
        'module "m" {\n  trigger "t" {\n    on CARD_ADDED;\n    let y: int = 1;\n    '
        + body
        + "\n  }\n}\n"
    )


def _diagnostics(body: str):
    return validate_source(_wrap(body), filename="x.aa2m").diagnostics


def _offset(source: str, line: int, column: int) -> int:
    lines = source.split("\n")
    return sum(len(item) + 1 for item in lines[: line - 1]) + column - 1


def _apply(source: str, fix) -> str:
    span = fix.span
    start = _offset(source, span.start_line, span.start_column)
    end = _offset(source, span.end_line, span.end_column) + 1
    return source[:start] + fix.replacement + source[end:]


# body, diagnostic code, help substring, fix replacements
SYNTAX_HINTS = [
    ("if y = 3 { }", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("if (y = 3) { }", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("if y == 1 { } else if y = 2 { }", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("break if y = 1;", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("loop { break if y = 1; }", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("let q: bool = y = 1;", "SYNTAX_ERROR", "use `==` to compare", ["=="]),
    ("y += 1;", "SYNTAX_ERROR", "aa2m has no `+=`", ["y = y + 1"]),
    ("y -= 2;", "SYNTAX_ERROR", "aa2m has no `-=`", ["y = y - 2"]),
    ("y *= 2;", "SYNTAX_ERROR", "aa2m has no `*=`", ["y = y * 2"]),
    ("y /= 2;", "SYNTAX_ERROR", "aa2m has no `/=`", ["y = y / 2"]),
    ("y += 1 + 2;", "SYNTAX_ERROR", "aa2m has no `+=`", ["y = y + (1 + 2)"]),
    ("y++;", "SYNTAX_ERROR", "aa2m has no `++`", ["y = y + 1"]),
    ("y--;", "SYNTAX_ERROR", "aa2m has no `--`", ["y = y - 1"]),
    ("if y > 1 and y < 3 { }", "SYNTAX_ERROR", "use `&&`", ["&&"]),
    ("if y > 1 or y < 3 { }", "SYNTAX_ERROR", "use `||`", ["||"]),
    ("if not y { }", "SYNTAX_ERROR", "use `!` for negation", []),
    ("if y == 1 { } elif y == 2 { }", "SYNTAX_ERROR", "write `else if condition", ["else if"]),
    ("if y == 1 { } elsif y == 2 { }", "SYNTAX_ERROR", "write `else if condition", ["else if"]),
    (
        "if y == 1 { }\n    elseif y == 2 { }",
        "SYNTAX_ERROR",
        "write `else if condition",
        ["else if"],
    ),
    ("if y == 1 { } elseif (y == 2) { }", "SYNTAX_ERROR", "write `else if condition", []),
    ("if y == 1 { } elif (y == 2) { }", "UNKNOWN_ACTION_NAME", "write `else if condition", []),
    ("let z = 1;", "SYNTAX_ERROR", "declarations need a type", []),
    ("WriteLog('hi');", "SYNTAX_ERROR", 'strings use double quotes: "text"', ['"hi"']),
    ("return;", "SYNTAX_ERROR", "aa2m has no `return`", []),
    ("function f() {}", "SYNTAX_ERROR", "define a `macro`", []),
    ("def f() {}", "SYNTAX_ERROR", "define a `macro`", []),
    ("fn f() {}", "SYNTAX_ERROR", "define a `macro`", []),
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
    first = _diagnostics(body)[0]

    assert first.code == code
    assert first.help is not None
    assert help in first.help
    assert [fix.replacement for fix in first.fixes] == replacements


def test_elseif_call_form_is_a_reserved_name():
    first = _diagnostics("if y == 1 { } elseif (y == 2) { }")[0]

    assert first.message == "invalid source name 'elseif'"
    assert first.fixes == ()


def test_quote_fix_replaces_the_whole_literal():
    source = _wrap("WriteLog('hi');")
    (fix,) = validate_source(source, filename="x.aa2m").diagnostics[0].fixes

    assert _apply(source, fix).count('WriteLog("hi");') == 1


def test_while_fix_rewrites_the_header_keeping_indentation():
    first = _diagnostics("while (y < 3) {\n      y = y + 1;\n    }")[0]

    (fix,) = first.fixes
    assert fix.replacement == "loop {\n      break if !(y < 3);"
    assert (fix.span.start_line, fix.span.start_column) == (5, 5)
    assert fix.span.end_line == 5


FIXABLE = [item for item in SYNTAX_HINTS if item[3]]
WHILE_BODIES = [
    "while (y < 3) {\n      y = y + 1;\n      y = y + 2;\n    }",
    "while (y < 3) {\n    }",
    "while (y < 3) { }",
    "while (y < 3) {}",
    "while (y < 3) { y = y + 1; }",
]


@pytest.mark.parametrize(
    "body",
    [item[0] for item in FIXABLE if not item[0].startswith("while")]
    + WHILE_BODIES
    + ["y += 1;\n    y *= 2 + 3;\n"],
)
def test_applying_the_fix_compiles_cleanly(body):
    source = _wrap(body)
    for _ in range(3):
        errors = validate_source(source, filename="x.aa2m").errors
        if not errors:
            break
        assert errors[0].fixes, errors[0]
        source = _apply(source, errors[0].fixes[0])
    assert source != _wrap(body)
    assert validate_source(source, filename="x.aa2m").errors == ()


def test_while_loop_rewrite_is_semantically_a_loop():
    source = _wrap("while (y < 3) {\n      y = y + 1;\n    }")
    (fix,) = validate_source(source, filename="x.aa2m").diagnostics[0].fixes

    assert _apply(source, fix) == _wrap("loop {\n      break if !(y < 3);\n      y = y + 1;\n    }")


def test_a_user_macro_named_while_still_works():
    source = (
        'macro "while" { param "c" int; WriteLog("x"); }\n'
        'module "m" { trigger "t" { on CARD_ADDED; while(1); } }\n'
    )

    result = validate_source(source, filename="x.aa2m")

    assert result.diagnostics == ()
