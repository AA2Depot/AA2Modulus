"""A call with one candidate reports every failing argument, in source order."""

from __future__ import annotations

from aa2modulus.app.compile import validate_source
from aa2modulus.context.limits import SourceLimits


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


def test_overloaded_call_still_reports_one_error():
    assert len(_errors("if Equal(a, b) { }")) == 1
    assert _summary('if Equal(1, "s") { }') == [
        ("SOURCE_TYPE_MISMATCH", "expected int, found string")
    ]


def test_single_bad_argument_keeps_its_single_diagnostic():
    errors = _errors("let x: int = Math.RandomInt(a, 1);")
    assert [(item.code, item.message) for item in errors] == _unknown("a")
    assert errors[0].line == 2
    assert _summary('let x: int = Math.RandomInt("s", 2);') == [
        ("SOURCE_TYPE_MISMATCH", "expected int, found string")
    ]


def test_error_cap_applies_to_argument_errors():
    codes = [
        item.code
        for item in _errors("(a).AddLike(b, c);", source_limits=SourceLimits(max_binding_errors=2))
    ]
    assert codes == [
        "UNKNOWN_EXPRESSION_NAME",
        "UNKNOWN_EXPRESSION_NAME",
        "SOURCE_BINDING_ERROR_LIMIT",
    ]
