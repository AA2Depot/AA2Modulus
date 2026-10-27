"""A failed parse reports every independent syntax error, first error unchanged."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source
from tests.support.source import multiline_module


def _diagnostics(source: str, **options):
    return validate_source(source, filename="x.aa2m", **options).diagnostics


def _positions(diagnostics):
    return [(item.line, item.column) for item in diagnostics]


def test_three_independent_errors_in_source_order():
    source = multiline_module(
        'WriteLog("a")\n    y = ;\n    WriteLog("b") WriteLog("c");\n    y = 1 +;'
    )
    diagnostics = _diagnostics(source)

    assert {item.code for item in diagnostics} == {"SYNTAX_ERROR"}
    assert [(item.line, item.column, item.message) for item in diagnostics] == [
        (5, 18, "expected `;`, `{`, or `.`, found `y`"),
        (7, 19, "expected `;`, `{`, or `.`, found `WriteLog`"),
        (8, 12, "expected an expression, found `;`"),
    ]


def test_missing_close_brace_before_second_trigger_is_one_error():
    source = (
        'module "m" {\n trigger "t" {\n on CARD_ADDED;\n WriteLog("a");\n'
        ' trigger "u" {\n on CARD_ADDED;\n }\n}\n'
    )
    diagnostics = _diagnostics(source)

    assert [(item.code, item.line, item.column) for item in diagnostics] == [
        ("SYNTAX_ERROR", 5, 10)
    ]
    assert diagnostics[0].message == 'expected `(` or `=`, found `"u"`'


def test_missing_open_brace_after_trigger_name_is_one_error():
    source = 'module "m" {\n trigger "t"\n on CARD_ADDED;\n WriteLog("a");\n }\n}\n'
    diagnostics = _diagnostics(source)

    assert [(item.code, item.line, item.column, item.message) for item in diagnostics] == [
        ("SYNTAX_ERROR", 3, 2, "expected `{`, found `on`")
    ]


def test_skipped_if_block_does_not_close_the_trigger():
    source = multiline_module('if (y = 3) { WriteLog("a"); }\n    y = ;\n    y = 1 +;')
    diagnostics = _diagnostics(source)

    assert [item.code for item in diagnostics] == ["SYNTAX_ERROR"] * 3
    assert _positions(diagnostics) == [(5, 11), (6, 9), (7, 12)]
    assert diagnostics[0].message == "unexpected `=`"


@pytest.mark.parametrize(
    ("source", "position", "message"),
    [
        # A missing terminator is reported right after the previous statement.
        (
            multiline_module('WriteLog("a")\n    y = 2;'),
            (5, 18),
            "expected `;`, `{`, or `.`, found `y`",
        ),
        (
            'module "m" {\n trigger "t" {\n on CARD_ADDED;\n',
            (4, 1),
            "expected `}`, found end of file",
        ),
        ('module "m" {\n trigger "t" {\n on CARD_ADDED\n }\n}\n', (3, 15), "unexpected `}`"),
        (multiline_module("y = 1 ` 2;"), (5, 11), "unexpected character ```"),
        (multiline_module('WriteLog("abc);'), (5, 14), "unterminated string literal"),
        (
            'module "m" {\n description """\n  a\n trigger "t" {\n on CARD_ADDED;\n }\n}\n',
            (2, 14),
            'unterminated block string; close it with `"""` on its own line',
        ),
    ],
    ids=[
        "missing-semicolon",
        "eof-without-brace",
        "unexpected-brace",
        "bad-char",
        "unterminated",
        "unterminated-block",
    ],
)
def test_single_syntax_error_is_reported_once_without_cascades(source, position, message):
    (diagnostic,) = _diagnostics(source)

    assert diagnostic.code == "SYNTAX_ERROR"
    assert (diagnostic.line, diagnostic.column) == position
    assert diagnostic.message == message


def test_lexer_and_parser_faults_combine_one_per_statement():
    diagnostics = _diagnostics(multiline_module("y = $;\n    WriteLog('a b);\n    y = ;"))

    assert [(item.code, item.line, item.column) for item in diagnostics] == [
        ("SYNTAX_ERROR", 5, 9),
        ("SYNTAX_ERROR", 6, 14),
        ("SYNTAX_ERROR", 7, 9),
    ]
    assert diagnostics[0].message == "unexpected character `$`, expected an expression"
    assert diagnostics[1].message == "unexpected character `'`"
    assert diagnostics[2].message == "expected an expression, found `;`"


def test_one_error_per_statement_segment():
    diagnostics = _diagnostics(multiline_module("y = $ $;\n    y = ;"))

    assert _positions(diagnostics) == [(5, 9), (6, 9)]


def test_error_count_is_capped_with_a_limit_diagnostic_after_twenty_five_by_default():
    source = multiline_module("\n    ".join(["y = ;"] * 30))
    diagnostics = _diagnostics(source)

    assert [item.code for item in diagnostics].count("SYNTAX_ERROR") == 25
    assert diagnostics[-1].code == "SOURCE_SYNTAX_ERROR_LIMIT"
    assert diagnostics[-1].message == "syntax checking stopped after 25 errors"


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (multiline_module("y = 99999999999999999999;"), "INT_OUT_OF_RANGE"),
        ('trigger "t" { on CARD_ADDED; }', "MODULE_REQUIRED"),
    ],
)
def test_transformer_level_errors_stay_single(source, code):
    assert [item.code for item in _diagnostics(source)] == [code]


LIBRARY = (
    'macro "a" { param "c" int; WriteLog(); WriteLog("x" ;\n}\n'
    'macro "b" { param "c" int; WriteLog(1 2); }\n'
)


def test_import_failure_reports_only_the_librarys_first_syntax_error(tmp_path):
    (tmp_path / "lib.aa2mi").write_text(LIBRARY, encoding="utf-8")

    diagnostics = _diagnostics('import "lib.aa2mi"; module "M" { }', import_base=tmp_path)

    assert [(item.code, item.line) for item in diagnostics] == [("SYNTAX_ERROR", 1)]
    assert diagnostics[0].filename.endswith("lib.aa2mi")
    assert diagnostics[0].message == "expected `)` or `,`, found `;`"


def test_validating_the_library_itself_reports_every_syntax_error(tmp_path):
    diagnostics = validate_source(
        LIBRARY, filename="lib.aa2mi", import_base=tmp_path, source_kind="library"
    ).diagnostics

    assert [(item.code, item.line, item.message) for item in diagnostics] == [
        ("SYNTAX_ERROR", 1, "expected `)` or `,`, found `;`"),
        ("SYNTAX_ERROR", 3, "expected `)` or `,`, found `2`"),
    ]
