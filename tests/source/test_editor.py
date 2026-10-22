"""Bounded editor recovery stays separate from strict source analysis."""

from __future__ import annotations

import pytest

from aa2modulus.context.limits import SourceLimitError
from aa2modulus.context.operation import SourceContext
from aa2modulus.pipeline.analysis import analyze_source
from aa2modulus.pipeline.authoring import analyze_authoring, parse_editor_unit
from aa2modulus.syntax.parser.errors import SourceParseError


def test_editor_recovery_keeps_complete_statements_around_unrelated_faults():
    context = SourceContext.create()
    source = 'module "M" { trigger "T" { Notification("before"); @ Notification("after"); } }'

    unit = parse_editor_unit(source, context)
    analysis = analyze_source(source, context=context)
    authoring = analyze_authoring(source, context, analysis=analysis)

    assert analysis.failure is not None
    assert not analysis.result.is_valid
    assert analysis.bound is None
    assert unit.module is not None
    assert len(unit.module.triggers[0].statements) == 2
    assert authoring.unit is not None
    assert [item.name for item in authoring.references if item.metadata is not None] == [
        "Notification",
        "Notification",
    ]


def test_editor_recovery_drops_only_the_unfinished_final_statement():
    context = SourceContext.create()
    source = 'module "M" { trigger "T" { Notification("complete"); Notification('

    unit = parse_editor_unit(source, context)

    assert unit.module is not None
    assert len(unit.module.triggers[0].statements) == 1
    assert isinstance(analyze_source(source, context=context).failure, SourceParseError)


def test_editor_recovery_keeps_float_bits_declarations_around_a_fault():
    context = SourceContext.create()
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


def test_editor_recovery_rejects_more_than_the_fault_budget():
    context = SourceContext.create()
    source = 'module "M" { trigger "T" { ' + " ".join("@" for _ in range(33)) + " } }"

    with pytest.raises(SourceLimitError) as error:
        parse_editor_unit(source, context)

    assert error.value.diagnostic.code == "EDITOR_RECOVERY_LIMIT"


def test_editor_recovery_keeps_scope_and_bindings_after_an_invalid_statement():
    context = SourceContext.create()
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


def test_unrecoverable_source_kind_conflict_has_no_partial_authoring_unit():
    context = SourceContext.create(filename="module.aa2m")
    source = 'trigger "T" { } module "M" {}'

    authoring = analyze_authoring(source, context)

    assert authoring.ast is None
    assert authoring.unit is None
    assert isinstance(authoring.failure, SourceParseError)
