"""A failed parse reports every independent syntax error, first error unchanged."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source
from aa2modulus.context.limits import SourceLimits
from aa2modulus.context.operation import SourceContext
from aa2modulus.pipeline.analysis import analyze_source
from aa2modulus.pipeline.authoring import analyze_authoring, parse_editor_unit
from aa2modulus.syntax.parser.errors import SourceParseError
from aa2modulus.syntax.parser.units import parse_source_unit


def _wrap(body: str) -> str:
    return (
        'module "m" {\n  trigger "t" {\n    on CARD_ADDED;\n    let y: int = 1;\n    '
        + body
        + "\n  }\n}\n"
    )


def _diagnostics(source: str, **options):
    return validate_source(source, filename="x.aa2m", **options).diagnostics


def _positions(diagnostics):
    return [(item.line, item.column) for item in diagnostics]


def test_three_independent_errors_in_source_order():
    source = _wrap('WriteLog("a")\n    y = ;\n    WriteLog("b") WriteLog("c");\n    y = 1 +;')
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
    source = _wrap('if (y = 3) { WriteLog("a"); }\n    y = ;\n    y = 1 +;')
    diagnostics = _diagnostics(source)

    assert [item.code for item in diagnostics] == ["SYNTAX_ERROR"] * 3
    assert _positions(diagnostics) == [(5, 11), (6, 9), (7, 12)]
    assert diagnostics[0].message == "unexpected `=`"


@pytest.mark.parametrize(
    "source",
    [
        _wrap('WriteLog("a")\n    y = 2;'),
        'module "m" {\n trigger "t" {\n on CARD_ADDED;\n',
        'module "m" {\n trigger "t" {\n on CARD_ADDED\n }\n}\n',
        _wrap("y = 1 ` 2;"),
        _wrap('WriteLog("abc);'),
    ],
    ids=["missing-semicolon", "eof-without-brace", "unexpected-brace", "bad-char", "unterminated"],
)
def test_single_error_matches_the_parsers_first_error(source):
    with pytest.raises(SourceParseError) as raised:
        parse_source_unit(source, filename="x.aa2m")
    first = raised.value

    (diagnostic,) = _diagnostics(source)

    assert diagnostic.code == first.code
    assert diagnostic.message == first.message
    assert (diagnostic.line, diagnostic.column) == (first.line, first.column)
    assert diagnostic.source_span == first.source_span
    assert diagnostic.help == first.help
    assert diagnostic.fixes == first.fixes


def test_first_error_of_a_multi_error_file_is_the_parsers_error():
    source = _wrap('y = ;\n    WriteLog("a") y = 2;\n    y = ;')
    with pytest.raises(SourceParseError) as raised:
        parse_source_unit(source, filename="x.aa2m")

    diagnostics = _diagnostics(source)

    assert len(diagnostics) == 3
    assert (diagnostics[0].line, diagnostics[0].column, diagnostics[0].message) == (
        raised.value.line,
        raised.value.column,
        raised.value.message,
    )
    assert diagnostics[0].source_span == raised.value.source_span


def test_lexer_and_parser_faults_combine_one_per_statement():
    diagnostics = _diagnostics(_wrap("y = $;\n    WriteLog('a b);\n    y = ;"))

    assert [(item.code, item.line, item.column) for item in diagnostics] == [
        ("SYNTAX_ERROR", 5, 9),
        ("SYNTAX_ERROR", 6, 14),
        ("SYNTAX_ERROR", 7, 9),
    ]
    assert diagnostics[0].message == "unexpected character `$`, expected an expression"
    assert diagnostics[1].message == "unexpected character `'`"
    assert diagnostics[2].message == "expected an expression, found `;`"


def test_one_error_per_statement_segment():
    diagnostics = _diagnostics(_wrap("y = $ $;\n    y = ;"))

    assert _positions(diagnostics) == [(5, 9), (6, 9)]


def test_error_count_is_capped_with_a_limit_diagnostic():
    source = _wrap("\n    ".join(["y = ;"] * 6))
    diagnostics = _diagnostics(source, source_limits=SourceLimits(max_syntax_errors=3))

    assert [item.code for item in diagnostics] == ["SYNTAX_ERROR"] * 3 + [
        "SOURCE_SYNTAX_ERROR_LIMIT"
    ]
    assert diagnostics[-1].message == "syntax checking stopped after 3 errors"
    assert _positions(diagnostics[:3]) == [(5, 9), (6, 9), (7, 9)]


def test_default_cap_is_twenty_five():
    assert SourceLimits().max_syntax_errors == 25
    source = _wrap("\n    ".join(["y = ;"] * 30))
    diagnostics = _diagnostics(source)

    assert [item.code for item in diagnostics].count("SYNTAX_ERROR") == 25
    assert diagnostics[-1].code == "SOURCE_SYNTAX_ERROR_LIMIT"
    assert diagnostics[-1].message == "syntax checking stopped after 25 errors"


def test_max_syntax_errors_must_be_positive():
    with pytest.raises(ValueError, match="max_syntax_errors must be at least 1"):
        SourceLimits(max_syntax_errors=0)
    assert SourceLimits(max_syntax_errors=1).max_syntax_errors == 1


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (_wrap("y = 99999999999999999999;"), "INT_OUT_OF_RANGE"),
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


def test_editor_views_still_work_on_a_broken_file():
    context = SourceContext.create()
    source = _wrap('WriteLog("a")\n    y = ;\n    WriteLog("b") WriteLog("c");')

    unit = parse_editor_unit(source, context)
    analysis = analyze_source(source, context=context)
    authoring = analyze_authoring(source, context, analysis=analysis)

    assert analysis.failure is not None
    assert len(analysis.result.errors) == 2
    assert unit.module is not None
    assert authoring.unit is not None
