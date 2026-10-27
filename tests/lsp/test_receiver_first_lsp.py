"""Editor support for receiver-first built-ins: member forms, properties, bare receivers."""

from __future__ import annotations

import pytest
from lsprotocol.types import CompletionItemKind, InsertTextFormat

from aa2modulus.app.compile import validate_source
from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.documentation.builtins import BuiltinDocumentation
from aa2modulus.lsp.features.navigation import definition, document_symbols, hover
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.signature.help import signature_help
from tests.support.lsp_workspace import apply_text_edit, open_document

_HEAD = 'module "M" { trigger "T" { on CARD_ADDED; let coach: card = ThisCard; '

# Every receiver kind the editor resolves, each written as a prefix ending in a dot.
_RECEIVERS = [
    "coach.",
    'variable("coach").',
    "(coach).",
    "ThisCard().",
    "coach.Target.",
    "(coach).Target.",
    "ThisCard.",
    "TriggeringCard.",
    "Globals.PlayerCharacter.",
]


def _labels(items):
    return {item.label: item for item in items}


def _assert_statement_position_offers_only_action_members(context, receiver):
    source = _HEAD + receiver
    items = completions(source, len(source), context, snippet_support=True)
    by_label = _labels(items)

    assert items
    assert all(item.kind == CompletionItemKind.Method for item in items)
    assert all(" -> " not in item.detail for item in items)
    assert "Virtue" not in by_label
    set_virtue = by_label["SetVirtue"]
    assert set_virtue.detail == "SetVirtue(value: int)"
    assert set_virtue.text_edit.new_text == "SetVirtue(${1:value});$0"
    assert set_virtue.insert_text_format == InsertTextFormat.Snippet


def _assert_value_position_offers_properties_without_parentheses(context, receiver):
    source = _HEAD + "let v: int = " + receiver
    items = completions(source, len(source), context, snippet_support=True)
    by_label = _labels(items)

    assert items and all(item.detail.endswith((" -> int", " -> card")) for item in items)
    assert "SetVirtue" not in by_label
    virtue = by_label["Virtue"]
    assert virtue.kind == CompletionItemKind.Property
    assert virtue.detail == "Virtue -> int"
    assert virtue.text_edit.new_text == "Virtue"
    assert virtue.insert_text == "Virtue"
    assert virtue.insert_text_format == InsertTextFormat.PlainText
    # Calls with arguments keep the snippet.
    love = by_label["Love"]
    assert love.kind == CompletionItemKind.Method
    assert love.text_edit.new_text == "Love(${1:towards})$0"
    assert love.insert_text_format == InsertTextFormat.Snippet
    # Properties compile when inserted verbatim.
    completed = source + "Virtue; } }"
    assert validate_source(completed, context=context).is_valid


def _assert_signature_help_hides_the_receiver_slot(context, receiver):
    source = _HEAD + receiver + "SetVirtue("
    help_ = signature_help(source, len(source), context)

    assert help_ is not None
    (signature,) = help_.signatures
    assert signature.label == "SetVirtue(value: int)"
    assert [signature.label[slice(*item.label)] for item in signature.parameters] == ["value: int"]
    assert help_.active_parameter == 0


@pytest.mark.parametrize("receiver", _RECEIVERS)
def test_every_receiver_form_resolves_for_actions_values_and_signatures(context, receiver):
    _assert_statement_position_offers_only_action_members(context, receiver)
    _assert_value_position_offers_properties_without_parentheses(context, receiver)
    _assert_signature_help_hides_the_receiver_slot(context, receiver)


def test_value_position_filters_members_by_expected_type(context):
    source = _HEAD + "let name: string = ThisCard."
    items = completions(source, len(source), context)
    assert items and all(item.detail.endswith(" -> string") for item in items)
    assert "FullName" in _labels(items)
    assert "Virtue" not in _labels(items)


def test_partial_member_edit_replaces_only_the_member_text(context):
    for receiver, partial in (
        ("coach.", "Vir"),
        ("TriggeringCard.", "Vi"),
        ("(coach).Target.", "Virt"),
    ):
        source = _HEAD + "let v: int = " + receiver + partial
        item = _labels(completions(source, len(source), context))["Virtue"]
        assert item.text_edit.new_text == "Virtue"
        assert apply_text_edit(source, item) == _HEAD + "let v: int = " + receiver + "Virtue"
        assert item.text_edit.range.start.character == len(_HEAD + "let v: int = " + receiver)


def test_member_edit_is_utf16_correct_for_bare_receivers(context):
    source = 'module "M😀" { trigger "T😀" { let v: int = TriggeringCard.Vir'
    item = _labels(completions(source, len(source), context))["Virtue"]
    # Each emoji is two UTF-16 code units; the source holds two of them.
    assert item.text_edit.range.start.character == source.index("Vir") + 2
    assert item.text_edit.range.end.character == len(source) + 2
    assert apply_text_edit(source, item) == source + "tue"


def test_member_canonical_targets_are_never_offered_as_flat_names(context):
    flat = {"SetVirtue", "Virtue", "FullName", "AddLike", "Character.SetVirtue", "Character.Virtue"}
    for tail in ("", "Set", "Char", "Character.", "Context.", "Context.Trig", "Globals."):
        for prefix in (_HEAD, _HEAD + "let v: int = ", _HEAD + "let s: string = "):
            source = prefix + tail
            labels = {item.label for item in completions(source, len(source), context)}
            assert not labels & flat, (prefix, tail)
            assert not any(label.startswith("Character.") for label in labels)


def test_namespace_built_ins_and_bare_receivers_coexist_after_context_dot(context):
    source = _HEAD + "let v: int = Context."
    labels = {item.label for item in completions(source, len(source), context)}
    assert "Context.NpcTalkTarget" in labels
    assert all(label.startswith("Context.") for label in labels)
    members = _HEAD + "let v: int = Context.NpcTalkTarget."
    assert "Virtue" in {item.label for item in completions(members, len(members), context)}


def test_non_receivers_offer_no_members(context):
    for tail in ("missing.", "Context.Unknown.", 'let label: string = "x"; label.'):
        source = _HEAD + tail
        assert completions(source, len(source), context) == [], tail


def test_signature_help_tracks_arguments_and_skips_properties(context):
    source = _HEAD + "TriggeringCard.AddLike(coach, "
    help_ = signature_help(source, len(source), context)
    assert help_ is not None and help_.active_parameter == 1
    assert help_.signatures[0].label == "AddLike(towards: card, amount: int)"
    # A property takes no parentheses: there is no signature to show.
    value = _HEAD + "let v: int = ThisCard.Virtue("
    assert signature_help(value, len(value), context) is None


_SOURCE = (
    _HEAD
    + "coach.SetVirtue(3); let v: int = ThisCard.Virtue; "
    + "let w: int = TriggeringCard.Target.Virtue; "
    + "TriggeringCard.AddLike(coach, 5); } }"
)


def test_hover_and_definition_cover_member_and_property_names(context):
    documentation = BuiltinDocumentation(context.metadata, enabled=True)
    workspace, snapshot = open_document(_SOURCE, context)
    codec = PositionCodec(_SOURCE)

    def at(text, member):
        return codec.position(_SOURCE.index(text) + text.index(member))

    cases = [
        ("coach.SetVirtue(3)", "SetVirtue", "<card>.SetVirtue(value: int)"),
        ("ThisCard.Virtue", "Virtue", "<card>.Virtue -> int"),
        ("Target.Virtue", "Virtue", "<card>.Virtue -> int"),
        ("TriggeringCard.AddLike", "AddLike", "<card>.AddLike(towards: card, amount: int)"),
    ]
    for text, member, signature in cases:
        position = at(text, member)
        result = hover(snapshot, position, "utf-16")
        assert result is not None, text
        assert signature in result.contents.value, text
        assert result.range.start == position
        assert result.range.end.character - result.range.start.character == len(member)
        assert "Native target:" in result.contents.value

    like = hover(snapshot, at("AddLike(coach", "AddLike"), "utf-16")
    assert "Adds a certain amount of like points." in like.contents.value
    (target,) = definition(
        snapshot, at("AddLike(coach", "AddLike"), "utf-16", workspace, documentation=documentation
    )
    assert target.uri == "aa2m-builtin:/action-13.md"


def test_hover_without_guide_and_receiver_variable_hover(context):
    _, snapshot = open_document(_SOURCE, context)
    codec = PositionCodec(_SOURCE)
    result = hover(snapshot, codec.position(_SOURCE.index("Virtue;")), "utf-16")
    assert result is not None and "<card>.Virtue -> int" in result.contents.value
    receiver = hover(snapshot, codec.position(_SOURCE.index("coach.SetVirtue")), "utf-16")
    assert receiver is not None and "coach: card" in receiver.contents.value
    declaration = hover(snapshot, codec.position(_SOURCE.index("coach: card")), "utf-16")
    assert declaration is not None and "coach: card" in declaration.contents.value


def test_document_symbols_accept_property_syntax(context):
    _, snapshot = open_document(_SOURCE, context)
    assert [symbol.name for symbol in document_symbols(snapshot, "utf-16")] == ["M"]
    _, broken = open_document(_HEAD + "let v: int = ThisCard.Virtue(; ", context)
    assert [symbol.name for symbol in document_symbols(broken, "utf-16")] == ["M"]


def _argument_labels(context, tail):
    source = _HEAD + tail
    return {item.label for item in completions(source, len(source), context)}


def test_member_argument_slots_filter_by_the_selected_parameter_type(context):
    int_labels = _argument_labels(context, "coach.SetVirtue(")
    assert "Globals.CurrentDay" in int_labels
    assert "Context.DelayedEventLabel" not in int_labels

    string_labels = _argument_labels(context, "coach.SetFirstName(")
    assert "Context.DelayedEventLabel" in string_labels
    assert "Globals.CurrentDay" not in string_labels
    # A card receiver fits through a member such as ``coach.FirstName``.
    assert "coach" in string_labels


def test_member_overload_uses_the_expected_result_type(context):
    int_labels = _argument_labels(context, 'let v: int = coach.GetInt("key", ')
    string_labels = _argument_labels(context, 'let v: string = coach.GetString("key", ')
    assert "Globals.CurrentDay" in int_labels
    assert "Context.DelayedEventLabel" not in int_labels
    assert "Context.DelayedEventLabel" in string_labels
    assert "Globals.CurrentDay" not in string_labels


def test_member_call_with_all_arguments_offers_nothing_more(context):
    assert not _argument_labels(context, "ThisCard.AddLike(coach, 3, ")


def test_card_result_roles_show_in_hover_and_completion_documentation(context):
    source = (
        _HEAD
        + "let a: int = Context.NpcAnswerTarget; let t: int = coach.Target; "
        + "let r: int = Context.NpcRoomTarget; } }"
    )
    _, snapshot = open_document(source, context)
    codec = PositionCodec(source)

    def text_at(needle):
        result = hover(snapshot, codec.position(source.index(needle)), "utf-16")
        assert result is not None, needle
        return result.contents.value

    assert "Returns: card" in text_at("NpcAnswerTarget;")
    assert "Returns: card" in text_at("Target; let r")
    assert "Returns:" not in text_at("NpcRoomTarget")

    head = _HEAD + "let v: int = "
    items = _labels(completions(head, len(head), context))
    assert items["ThisCard"].documentation.value.startswith("Returns: card")
    members = _labels(completions(head + "coach.", len(head) + 6, context))
    assert "Returns: card" in members["Target"].documentation.value


def _ranked(context, tail):
    source = _HEAD + tail
    items = completions(source, len(source), context)
    return [item.label for item in sorted(items, key=lambda item: item.sort_text or item.label)]


# Flat built-ins whose result role is card.
_CARD_BUILT_INS = {
    "ThisCard",
    "TriggeringCard",
    "Context.NpcAnswerTarget",
    "Context.NpcTalkTarget",
    "Context.NpcTalkAbout",
    "Context.RelationshipTowards",
    "Conversation.Actor",
    "Conversation.PcTalkAbout",
    "Globals.FindSeat",
    "Globals.PcTarget",
    "Globals.PlayerCharacter",
    "H.ActiveActor",
    "H.PassiveActor",
    "H.DominantActor",
    "H.SubmissiveActor",
}


def test_card_arguments_rank_card_valued_built_ins_first(context):
    ranked = _ranked(context, "coach.AddLike(")
    assert set(ranked[: len(_CARD_BUILT_INS)]) == _CARD_BUILT_INS
    # Ranking never filters: other int values, variables included, follow.
    assert {"coach", "Globals.CurrentDay"} <= set(ranked)
    assert _ranked(context, "coach.AddLike(H")[:4] == [
        "H.ActiveActor",
        "H.DominantActor",
        "H.PassiveActor",
        "H.SubmissiveActor",
    ]


@pytest.mark.parametrize(
    "tail",
    ["let filled: bool = Globals.IsSeatFilled(", "Check("],
    ids=["flat-slot", "macro-formal"],
)
def test_card_arguments_rank_cards_before_other_values_without_filtering(context, tail):
    prefix = (
        'macro Check { param seat card; } module "Cards" { trigger "T" { '
        "on CARD_ADDED; let coach: card = ThisCard; let amount: int = 4; "
    )
    source = prefix + tail
    items = completions(source, len(source), context)
    labels = [item.label for item in sorted(items, key=lambda item: item.sort_text or item.label)]

    assert max(labels.index("coach"), labels.index("ThisCard")) < min(
        labels.index("amount"), labels.index("Globals.CurrentDay")
    )


def test_flat_card_parameters_are_named_in_signature_help(context):
    source = _HEAD + "let filled: bool = Globals.IsSeatFilled("
    help_ = signature_help(source, len(source), context)

    assert help_ is not None
    assert help_.signatures[0].label == "Globals.IsSeatFilled(seat: card)"


@pytest.mark.parametrize(
    "tail", ["coach.AddLike(ThisCard, ", "coach.SetVirtue(", "coach.AddLike(1 + ", "let v: int = "]
)
def test_positions_without_a_card_role_are_not_ranked(context, tail):
    source = _HEAD + tail
    assert all(item.sort_text is None for item in completions(source, len(source), context))


def test_statement_start_offers_card_built_ins_as_receivers(context):
    items = completions(_HEAD, len(_HEAD), context, snippet_support=True)
    expressions = {
        item.label: item
        for item in items
        if item.kind in {CompletionItemKind.Property, CompletionItemKind.Function}
        and item.detail.endswith(" -> card")
    }

    assert set(expressions) == _CARD_BUILT_INS
    assert not {"Globals.CurrentDay", "Text.Length"} & {item.label for item in items}
    # A receiver is continued with a member: no parentheses, no terminator.
    this_card = expressions["ThisCard"]
    assert this_card.text_edit.new_text == "ThisCard"
    assert this_card.insert_text_format == InsertTextFormat.PlainText
    assert expressions["Conversation.Actor"].text_edit.new_text == "Conversation.Actor(${1:0})$0"


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [("Th", {"ThisCard"}), ("Tr", {"TriggeringCard"}), ("Globals.Pl", {"Globals.PlayerCharacter"})],
)
def test_statement_prefix_completes_card_receivers(context, prefix, expected):
    source = _HEAD + prefix
    assert {item.label for item in completions(source, len(source), context)} == expected


def test_statement_start_card_variables_stay_bare(context):
    source = _HEAD + "let n: int = 0; "
    edits = {
        item.label: item.text_edit.new_text
        for item in completions(source, len(source), context)
        if item.kind == CompletionItemKind.Variable
    }

    assert edits["coach"] == "coach"
    assert edits["n"] == "n = "


def test_statement_start_offers_card_macro_formals(context):
    before = 'macro "m" { param c card; param n int; '
    source = before + '}\nmodule "M" { trigger "T" { on CARD_ADDED; } }\n'
    variables = {
        item.label: item.text_edit.new_text
        for item in completions(source, len(before), context)
        if item.kind == CompletionItemKind.Variable
    }

    assert variables == {"c": "c"}


@pytest.mark.parametrize("tail", ["Notification(", "let s: string = ", "let f: float = "])
def test_value_slots_offer_card_receivers_after_matching_values(context, tail):
    ranked = _ranked(context, tail)
    receivers = _CARD_BUILT_INS | {"coach"}

    assert set(ranked[-len(receivers) :]) == receivers


def test_value_slot_card_receiver_inserts_the_bare_name(context):
    source = _HEAD + "Notification(Th"
    items = completions(source + "); } }", len(source), context, snippet_support=True)

    assert [(item.label, item.text_edit.new_text) for item in items] == [("ThisCard", "ThisCard")]
