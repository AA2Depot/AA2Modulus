"""Structured diagnostic fixes: each edit applies to the source and clears its finding."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import parse_and_validate_source
from aa2modulus.core.diagnostics import Diagnostic
from tests.support.source import apply_fix, module_source

# A quoted global that collides with a constant makes the bare name ambiguous.
COLLIDING = 'global "K": int = 0; const K: int = 7;'
RAW_COUNTER = 'raw_action 1(raw_expression int 2 { variable "counter"; }, 1);'


def _diagnostics(source: str, **options) -> tuple[Diagnostic, ...]:
    _, result = parse_and_validate_source(source, **options)
    return result.diagnostics


@pytest.mark.parametrize(
    ("source", "code", "help", "expected"),
    (
        (
            module_source("SetVirtue(ThisCard, 3);"),
            "UNKNOWN_ACTION_NAME",
            "use 'ThisCard.SetVirtue(3)'",
            ["ThisCard.SetVirtue(3);"],
        ),
        (
            module_source("AddLikePoints(ThisCard,\n    TriggeringCard, 3);"),
            "UNKNOWN_ACTION_NAME",
            "use 'ThisCard.AddLike(TriggeringCard, 3)'",
            ["ThisCard.AddLike(TriggeringCard, 3);"],
        ),
        (
            module_source("let a: int = LovePoints(ThisCard, ThisCard);"),
            "UNKNOWN_EXPRESSION_NAME",
            "use 'ThisCard.Love(ThisCard)'",
            ["let a: int = ThisCard.Love(ThisCard);"],
        ),
        (
            module_source("let a: int = globals.CurrentDay;"),
            "UNKNOWN_EXPRESSION_NAME",
            "namespace roots are case-sensitive; did you mean 'Globals.CurrentDay'?",
            ["let a: int = Globals.CurrentDay;"],
        ),
        (
            module_source('let n: int = classstorage.getint("x", 0);'),
            "UNKNOWN_EXPRESSION_NAME",
            "namespace roots are case-sensitive; did you mean 'ClassStorage.GetInt'?",
            ['let n: int = ClassStorage.GetInt("x", 0);'],
        ),
        (
            module_source("globals.setautopc(true);"),
            "UNKNOWN_ACTION_NAME",
            "namespace roots are case-sensitive; did you mean 'Globals.SetAutoPc'?",
            ["Globals.SetAutoPc(true);"],
        ),
        (
            module_source("ThisCard = 3;", 'global "ThisCard": int = 0;'),
            "PROTECTED_NAME",
            'assign a native variable of this name with variable("ThisCard")',
            ['variable("ThisCard") = 3;'],
        ),
        (
            module_source(RAW_COUNTER),
            "UNDEFINED_VARIABLE",
            "declare it in this module: `global counter: int = 0;`",
            ["global counter: int = 0;\n\n"],
        ),
        (
            module_source(RAW_COUNTER, "global other: bool = false;"),
            "UNDEFINED_VARIABLE",
            "declare it in this module: `global counter: int = 0;`",
            ["global other: bool = false;\n"],
        ),
    ),
)
def test_each_fix_rewrites_the_source_and_clears_the_finding(source, code, help, expected):
    # An assignment reports its undefined target and the same variable's read.
    diagnostic, *repeats = _diagnostics(source)
    assert {diagnostic.code, *(item.code for item in repeats)} == {code}
    assert diagnostic.help == help
    fixed = [apply_fix(source, fix) for fix in diagnostic.fixes]
    assert [text for text in expected if any(text in item for item in fixed)] == expected
    assert len(fixed) == len(expected)
    for text in fixed:
        assert _diagnostics(text) == ()


@pytest.mark.parametrize(
    ("source", "options"),
    (
        # A bare card-first name has no receiver to move.
        (module_source("let a: int = LovePoints;"), {}),
        # Member actions cannot take a block.
        (module_source("SetVirtue(ThisCard, 3) { }"), {}),
        (module_source("Missing();"), {}),
    ),
)
def test_findings_without_one_concrete_edit_carry_no_fix(source, options):
    (diagnostic,) = _diagnostics(source, **options)
    assert diagnostic.fixes == ()


@pytest.mark.parametrize(
    ("body", "expected"),
    (
        ("let x: int = K;", ['let x: int = const("K");', 'let x: int = variable("K");']),
        ("K = 1;", ['variable("K") = 1;']),
        # For-loop targets take no explicit const/variable form.
        ("for K from 0 to 2 { }", []),
    ),
)
def test_ambiguous_constant_fixes_name_one_meaning(body, expected):
    source = module_source(body, COLLIDING)
    collision, ambiguous = _diagnostics(source)
    assert (collision.code, ambiguous.code) == ("CONST_NAME_COLLISION", "AMBIGUOUS_CONST")
    fixed = [apply_fix(source, fix) for fix in ambiguous.fixes]
    assert [text for text in expected if any(text in item for item in fixed)] == expected
    assert len(fixed) == len(expected)
    for text in fixed:
        assert [item.code for item in _diagnostics(text)] == ["CONST_NAME_COLLISION"]
