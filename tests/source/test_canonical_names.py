"""A target with a canonical spelling accepts only that spelling."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import parse_and_validate_source
from tests.support.source import module_source


def _diagnostics(body: str, event: str = "CARD_ADDED"):
    _, result = parse_and_validate_source(module_source(body, event=event))
    return result.diagnostics


@pytest.mark.parametrize(
    ("body", "code", "canonical"),
    (
        ("ConditionalEndExecution(true);", "UNKNOWN_ACTION_NAME", "StopThreadIf"),
        ("End();", "UNKNOWN_ACTION_NAME", "StopThread"),
        ("let a: float = IntToFloat(3);", "UNKNOWN_EXPRESSION_NAME", "ToFloat"),
        ("let a: int = NpcTalkTarget;", "UNKNOWN_EXPRESSION_NAME", "Context.NpcTalkTarget"),
        ("let a: int = AnswerTarget;", "UNKNOWN_EXPRESSION_NAME", "Context.NpcAnswerTarget"),
        ("let a: int = LOVE;", "UNKNOWN_EXPRESSION_NAME", "Constants.Relationship.LOVE"),
        ("let a: int = EXAM;", "REJECTED_CONSTANT_NAME", "Constants.Period.EXAM"),
        (
            "let c: int = ThisCard; c.AddLikePoints(ThisCard, 3);",
            "UNKNOWN_MEMBER",
            "AddLike",
        ),
    ),
)
def test_native_fallback_is_rejected_with_the_canonical_hint(body, code, canonical):
    (diagnostic,) = _diagnostics(body)
    assert diagnostic.code == code
    assert canonical in diagnostic.help


def test_card_first_spelling_without_a_receiver_argument_gets_the_generic_member_hint():
    (diagnostic,) = _diagnostics("let a: int = LovePoints(ThisCard);")
    assert diagnostic.code == "UNKNOWN_EXPRESSION_NAME"
    assert "use '<card>.Love(...)'" in diagnostic.help
    assert "Character." not in diagnostic.help


def test_native_event_name_is_rejected_with_the_symbol_hint():
    (diagnostic,) = _diagnostics("", event="CardAddedToClass")
    assert diagnostic.code == "UNKNOWN_EVENT_NAME"
    assert "use 'CARD_ADDED'" in diagnostic.help


def test_a_genuinely_unknown_name_gets_no_hint():
    (diagnostic,) = _diagnostics("NoSuchAction();")
    assert diagnostic.help is None
