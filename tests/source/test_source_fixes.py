"""Structured diagnostic fixes: each edit applies to the source and clears its finding."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import parse_and_validate_source
from aa2modulus.core.diagnostics import Diagnostic, SourceFix

# A quoted global that collides with a constant makes the bare name ambiguous.
COLLIDING = 'global "K": int = 0; const K: int = 7;'
RAW_COUNTER = 'raw_action 1(raw_expression int 2 { variable "counter"; }, 1);'


def _module(body: str, items: str = "") -> str:
    return f'module "M" {{ {items} trigger "T" {{ on CARD_ADDED; {body} }} }}'


def _diagnostics(source: str, **options) -> tuple[Diagnostic, ...]:
    _, result = parse_and_validate_source(source, **options)
    return result.diagnostics


def _apply(source: str, fix: SourceFix) -> str:
    lines = source.splitlines(keepends=True)

    def offset(line: int, column: int) -> int:
        return sum(len(item) for item in lines[: line - 1]) + column - 1

    span = fix.span
    assert span.end_line is not None and span.end_column is not None
    start = offset(span.start_line, span.start_column)
    end = offset(span.end_line, span.end_column) + 1
    return source[:start] + fix.replacement + source[end:]


@pytest.mark.parametrize(
    ("source", "code", "expected", "options"),
    (
        (
            _module("SetVirtue(ThisCard, 3);"),
            "UNKNOWN_ACTION_NAME",
            ["ThisCard.SetVirtue(3);"],
            {},
        ),
        (
            _module("AddLikePoints(ThisCard,\n    TriggeringCard, 3);"),
            "UNKNOWN_ACTION_NAME",
            ["ThisCard.AddLike(TriggeringCard, 3);"],
            {},
        ),
        (
            _module("let a: int = LovePoints(ThisCard, ThisCard);"),
            "UNKNOWN_EXPRESSION_NAME",
            ["let a: int = ThisCard.Love(ThisCard);"],
            {},
        ),
        (
            _module("let a: int = globals.CurrentDay;"),
            "UNKNOWN_EXPRESSION_NAME",
            ["let a: int = Globals.CurrentDay;"],
            {},
        ),
        (
            _module("let a: int = context.npctalktarget;"),
            "UNKNOWN_EXPRESSION_NAME",
            ["let a: int = Context.NpcTalkTarget;"],
            {},
        ),
        (
            _module('let n: int = classstorage.getint("x", 0);'),
            "UNKNOWN_EXPRESSION_NAME",
            ['let n: int = ClassStorage.GetInt("x", 0);'],
            {},
        ),
        (
            _module("globals.setautopc(true);"),
            "UNKNOWN_ACTION_NAME",
            ["Globals.SetAutoPc(true);"],
            {},
        ),
        (
            _module("h.Start(ThisCard, TriggeringCard);"),
            "UNKNOWN_ACTION_NAME",
            ["H.Start(ThisCard, TriggeringCard);"],
            {},
        ),
        (
            _module("ThisCard = 3;", 'global "ThisCard": int = 0;'),
            "PROTECTED_NAME",
            ['variable("ThisCard") = 3;'],
            {},
        ),
        (
            _module(RAW_COUNTER),
            "UNDEFINED_VARIABLE",
            ["global counter: int = 0;\n\n"],
            {},
        ),
        (
            _module(RAW_COUNTER, "global other: bool = false;"),
            "UNDEFINED_VARIABLE",
            ["global other: bool = false;\n"],
            {},
        ),
    ),
)
def test_each_fix_rewrites_the_source_and_clears_the_finding(source, code, expected, options):
    # An assignment reports its undefined target and the same variable's read.
    diagnostic, *repeats = _diagnostics(source, **options)
    assert {diagnostic.code, *(item.code for item in repeats)} == {code}
    assert diagnostic.help
    fixed = [_apply(source, fix) for fix in diagnostic.fixes]
    assert [text for text in expected if any(text in item for item in fixed)] == expected
    assert len(fixed) == len(expected)
    for text in fixed:
        assert _diagnostics(text, **options) == ()


@pytest.mark.parametrize(
    ("source", "options"),
    (
        # A bare card-first name has no receiver to move.
        (_module("let a: int = LovePoints;"), {}),
        # Member actions cannot take a block.
        (_module("SetVirtue(ThisCard, 3) { }"), {}),
        (_module("Missing();"), {}),
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
    source = _module(body, COLLIDING)
    collision, ambiguous = _diagnostics(source)
    assert (collision.code, ambiguous.code) == ("CONST_NAME_COLLISION", "AMBIGUOUS_CONST")
    fixed = [_apply(source, fix) for fix in ambiguous.fixes]
    assert [text for text in expected if any(text in item for item in fixed)] == expected
    assert len(fixed) == len(expected)
    for text in fixed:
        assert [item.code for item in _diagnostics(text)] == ["CONST_NAME_COLLISION"]
