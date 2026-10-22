"""Namespace roots use exact case while their qualified names remain readable."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import compile_source
from aa2modulus.semantics.binding.state import SourceBindingError
from tests.support.source import parse_module


def _module(body: str) -> str:
    return f'module "M" {{ trigger "T" {{ on CARD_ADDED; {body} }} }}'


def test_only_namespace_root_case_is_significant():
    exact = _module("let who: int = Context.NpcTalkTarget;")
    folded_tail = _module("let who: int = Context.npctalktarget;")
    assert compile_source(exact) == compile_source(folded_tail)


@pytest.mark.parametrize("name", ("context.NpcTalkTarget", "CONTEXT.npctalktarget"))
def test_wrong_case_namespace_root_is_an_unknown_name_with_root_hint(name):
    with pytest.raises(SourceBindingError) as raised:
        parse_module(_module(f"let who: int = {name};"))
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "UNKNOWN_EXPRESSION_NAME"
    assert "case-sensitive" in diagnostic.help
    assert "Context" in diagnostic.help


@pytest.mark.parametrize(
    ("name", "hint"),
    (
        ("context.npctalktarget", "Context.NpcTalkTarget"),
        ("CONTEXT.NPCTALKTARGET", "Context.NpcTalkTarget"),
        # An unknown tail keeps the root-only correction.
        ("context.zzz", "Context.zzz"),
    ),
)
def test_root_hint_names_the_whole_canonical_spelling_when_the_tail_resolves(name, hint):
    with pytest.raises(SourceBindingError) as raised:
        parse_module(_module(f"let who: int = {name};"))
    assert f"did you mean {hint!r}?" in raised.value.diagnostic.help


def test_wrong_case_root_in_call_and_action_is_rejected():
    with pytest.raises(SourceBindingError) as call:
        parse_module(_module('let n: int = classstorage.GetInt("x", 0);'))
    assert call.value.diagnostic.code == "UNKNOWN_EXPRESSION_NAME"
    with pytest.raises(SourceBindingError) as action:
        parse_module(_module("globals.SetAutoPc(true);"))
    assert action.value.diagnostic.code == "UNKNOWN_ACTION_NAME"


def test_variable_names_remain_exact_and_do_not_retarget_registered_namespaces():
    source = _module(
        "let Context: int = ThisCard; let context: int = Context.NpcTalkTarget; "
        "let who: int = context;"
    )
    module = parse_module(source)
    assert module.triggers[0].variables[1].default_expression.id == 15
    assert module.triggers[0].variables[2].default_expression.id == 2
    assert module.triggers[0].variables[2].default_expression.variable_name == "context"
    compile_source(source)
