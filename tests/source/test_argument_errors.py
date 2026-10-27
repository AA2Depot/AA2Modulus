"""A call with one candidate reports every failing argument, in source order."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source


def _errors(body: str, prelude: str = "", **options):
    source = f'{prelude}module "M" {{ trigger "T" {{ on CARD_ADDED;\n{body}\n}} }}'
    return validate_source(source, filename="args.aa2m", **options).errors


def _summary(body: str, prelude: str = "", **options) -> list[tuple[str, str]]:
    return [(item.code, item.message) for item in _errors(body, prelude, **options)]


def _unknown(*names: str) -> list[tuple[str, str]]:
    return [("UNKNOWN_EXPRESSION_NAME", f"unknown source name {name!r}") for name in names]


def test_action_reports_every_bad_argument_in_source_order():
    assert _summary("JumpIf(a, b);") == _unknown("a", "b")


def test_single_overload_expression_reports_every_bad_argument():
    assert _summary("let x: int = Math.RandomInt(a, b);") == _unknown("a", "b")


def test_nested_calls_report_all_arguments():
    body = "let x: int = Math.RandomInt(Math.RandomInt(a, b), c);"
    assert _summary(body) == _unknown("a", "b", "c")


def test_member_call_reports_receiver_and_explicit_arguments():
    assert _summary("(a).AddLike(b, c);") == _unknown("a", "b", "c")
    assert _summary("Card(Math.RandomInt(1, 2)).AddLike(a, b);") == _unknown("a", "b")


def test_macro_call_reports_every_bad_argument_with_notes():
    prelude = 'macro "f" { param "p" card; param "q" int; ThisCard.AddLike(p, q); }\n'
    errors = _errors("f(a, b);", prelude)
    assert [(item.code, item.message) for item in errors] == _unknown("a", "b")
    for item, formal in zip(errors, ("p", "q"), strict=True):
        messages = [note.message for note in item.related]
        assert f"formal {formal!r} declared here" in messages
        assert "macro 'f' invoked here" in messages
        assert "macro defined here" in messages


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # An overloaded call reports its first bad argument only.
        ("if Equal(a, b) { }", _unknown("a")),
        ('if Equal(1, "s") { }', [("SOURCE_TYPE_MISMATCH", "expected int, found string")]),
        ("let x: int = Math.RandomInt(a, 1);", _unknown("a")),
        (
            'let x: int = Math.RandomInt("s", 2);',
            [("SOURCE_TYPE_MISMATCH", "expected int, found string")],
        ),
    ],
)
def test_one_bad_argument_or_an_overloaded_call_keeps_a_single_diagnostic(body, expected):
    errors = _errors(body)
    assert [(item.code, item.message) for item in errors] == expected
    assert errors[0].line == 2
