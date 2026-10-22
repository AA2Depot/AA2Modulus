"""Completion offers no native fallback spelling for a target with a canonical name."""

from __future__ import annotations

from lsprotocol.types import CompletionItemKind

from aa2modulus.lsp.completion.dispatch import completions

PREFIX = 'module "M" { trigger "T" { on CARD_ADDED; '


def _labels(source, context, kind=None):
    return {
        item.label
        for item in completions(source, len(source), context)
        if kind is None or item.kind == kind
    }


def test_statement_completion_lists_canonical_actions_only(context):
    labels = _labels(PREFIX, context, CompletionItemKind.Function)
    assert {"StopThreadIf", "Globals.SetPeriodTimer"} <= labels
    # Card-first actions are members of a card, never flat completion labels.
    assert not {"AddLikePoints", "ConditionalEndExecution"} & labels
    assert not {"Character.AddLike", "AddLike", "CardStorage.SetInt"} & labels


def test_event_completion_lists_symbols_only(context):
    labels = _labels('module "M" { trigger "T" { on ', context, CompletionItemKind.Event)
    assert "CARD_ADDED" in labels
    assert "CardAddedToClass" not in labels


def test_expression_completion_lists_canonical_names_only(context):
    labels = _labels(PREFIX + "let a: int = ", context)
    assert {"ToInt", "Context.NpcTalkTarget"} <= labels
    assert not {"LovePoints", "NpcTalkTarget", "LOVE"} & labels
    assert not {"Character.Love", "Love", "CardStorage.GetInt"} & labels
