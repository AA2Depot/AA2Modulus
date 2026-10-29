"""Bounded editor recovery stays separate from strict source analysis."""

from __future__ import annotations

import dataclasses

import pytest

from aa2modulus.context.limits import SourceLimitError
from aa2modulus.pipeline.analysis import analyze_source
from aa2modulus.pipeline.authoring import analyze_authoring, parse_editor_unit
from aa2modulus.syntax.parser.errors import SourceParseError
from tests.support.source import multiline_module


def test_editor_recovery_keeps_complete_statements_around_unrelated_faults(context):
    source = 'module "M" { trigger "T" { Notification("before"); @ Notification("after"); } }'

    unit = parse_editor_unit(source, context)
    analysis = analyze_source(source, context=context)
    authoring = analyze_authoring(source, context, analysis=analysis)

    assert isinstance(analysis.failure, SourceParseError)
    assert not analysis.result.is_valid
    assert analysis.bound is None
    assert unit.module is not None
    assert len(unit.module.triggers[0].statements) == 2
    assert authoring.unit is not None
    assert [item.name for item in authoring.references if item.metadata is not None] == [
        "Notification",
        "Notification",
    ]


def test_editor_recovery_keeps_valid_statements_between_several_syntax_errors(context):
    source = multiline_module(
        'WriteLog("a");\n    y = ;\n    WriteLog("b");\n    y = 1 +;\n    WriteLog("c");'
    )

    unit = parse_editor_unit(source, context)
    analysis = analyze_source(source, context=context)
    authoring = analyze_authoring(source, context, analysis=analysis)

    assert [(item.code, item.line) for item in analysis.result.errors] == [
        ("SYNTAX_ERROR", 6),
        ("SYNTAX_ERROR", 8),
    ]
    assert [item.source_span.start_line for item in unit.module.triggers[0].statements] == [5, 7, 9]
    assert [item.name for item in authoring.references] == [
        "CARD_ADDED",
        "WriteLog",
        "WriteLog",
        "WriteLog",
    ]


def test_editor_recovery_drops_only_the_unfinished_final_statement(context):
    source = 'module "M" { trigger "T" { Notification("complete"); Notification('

    unit = parse_editor_unit(source, context)

    assert unit.module is not None
    assert len(unit.module.triggers[0].statements) == 1
    assert isinstance(analyze_source(source, context=context).failure, SourceParseError)


def test_editor_recovery_keeps_float_bits_declarations_around_a_fault(context):
    source = (
        "const Pi: float = float_bits(0x3f800000);"
        ' module "M" { global g: float = float_bits(0x80000000);'
        ' trigger "T" { on CARD_ADDED; Notification( } }'
    )

    unit = parse_editor_unit(source, context)

    assert [item.name for item in unit.constants] == ["Pi"]
    assert unit.module is not None
    assert [item.name for item in unit.module.globals] == ["g"]
    assert unit.module.globals[0].default.value.bits == 0x80000000


def test_editor_recovery_rejects_more_than_the_fault_budget(context):
    source = 'module "M" { trigger "T" { ' + " ".join("@" for _ in range(33)) + " } }"

    with pytest.raises(SourceLimitError) as error:
        parse_editor_unit(source, context)

    assert error.value.diagnostic.code == "EDITOR_RECOVERY_LIMIT"


def test_editor_recovery_keeps_scope_and_bindings_after_an_invalid_statement(context):
    source = (
        'macro Local { param Value int; Notification("macro"); } '
        'module "M" { trigger "T" { let Count: int = 1; @ '
        'Notification("trigger"); Local(Count); } }'
    )
    analysis = analyze_source(source, context=context)

    authoring = analyze_authoring(source, context, analysis=analysis)

    assert authoring.unit is not None
    names = [item.name for item in authoring.references]
    assert names.count("Notification") == 2
    assert "Local" in names
    assert "Count" in names


def test_editor_view_keeps_triggers_after_a_stray_closing_brace_in_the_module(context):
    named = dataclasses.replace(context, filename="module.aa2m")
    source = (
        'module "M" {\n'
        "  global day: int = 0;\n"
        '  trigger "A" {\n'
        "    on CARD_ADDED;\n"
        "    if true { }\n"
        "    }\n"
        "  }\n"
        '  trigger "B" {\n'
        "    on CARD_ADDED;\n"
        "    day = 1;\n"
        "  }\n"
        "}\n"
    )
    analysis = analyze_source(source, context=named)

    authoring = analyze_authoring(source, named, analysis=analysis)

    assert isinstance(analysis.failure, SourceParseError)
    assert authoring.ast is not None
    assert authoring.ast.templates == ()
    module = authoring.ast.module
    assert [item.name for item in module.triggers] == ["A", "B"]
    assert (module.source_span.start_line, module.source_span.end_line) == (1, 11)
    day = [item for item in authoring.references if item.name == "day"]
    assert [(item.source_span.start_line, item.declaration is not None) for item in day] == [
        (10, True)
    ]
