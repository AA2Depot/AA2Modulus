"""Completion by statement, value and expected type, and the edits it applies."""

from __future__ import annotations

import json
import re

import pytest
from lsprotocol.types import CompletionItemKind

from aa2modulus.app.compile import validate_source
from aa2modulus.context.operation import SourceContext
from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.pipeline.analysis import analyze_source
from tests.support.lsp_workspace import apply_text_edit


@pytest.mark.parametrize(
    ("name", "statement"),
    [("true", False), ("name.with.dot", True), ('two words "quoted" 😀', False)],
)
def test_quoted_variable_completion_inserts_a_valid_reference(context, name, statement):
    declaration = json.dumps(name, ensure_ascii=False)
    before = f'module "M" {{ global {declaration}: int = 1; trigger "T" {{ '
    if not statement:
        before += "let copy: int = "
    source = before + ("} }" if statement else "; } }")
    item = next(
        item
        for item in completions(source, len(before), context)
        if item.label == name and item.kind == CompletionItemKind.Variable
    )
    codec = PositionCodec(source)
    start = codec.offset(item.text_edit.range.start)
    end = codec.offset(item.text_edit.range.end)
    insertion = item.text_edit.new_text + ("2;" if statement else "")
    completed = source[:start] + insertion + source[end:]

    assert item.text_edit.new_text.startswith("variable(")
    assert validate_source(completed, context=context).is_valid


def _labels(items, kind=None):
    return {item.label for item in items if kind is None or item.kind == kind}


def test_event_position_offers_canonical_events_and_no_actions(context):
    source = 'module "M" { trigger "T" { on '
    items = completions(source, len(source), context)
    events = _labels(items, CompletionItemKind.Event)

    assert {"CARD_ADDED", "CONVERSATION_END", "KEY_PRESS", "PC_RESPONSE"} <= events
    # Only the symbol spelling of an event is offered, and no action.
    assert not {"CardAddedToClass", "Notification", "WriteLog", "Globals.SetPeriodTimer"} & _labels(
        items
    )


def test_statement_position_offers_canonical_actions_and_keywords(context):
    source = 'module "M" { trigger "T" { on CARD_ADDED; '
    items = completions(source, len(source), context)
    actions = _labels(items, CompletionItemKind.Function)

    assert {"Notification", "WriteLog", "H.Start", "StopThreadIf", "Globals.SetPeriodTimer"} <= (
        actions
    )
    assert {"for", "if", "loop"} <= _labels(items, CompletionItemKind.Keyword)
    assert "CARD_ADDED" not in _labels(items)
    # Card-first actions are members of a card, never flat labels; neither are their
    # native spellings, nor the actions the language writes as statements.
    assert not {
        "AddLike",
        "AddLikePoints",
        "SetVirtue",
        "Character.AddLike",
        "CardStorage.SetInt",
        "ConditionalEndExecution",
        "SetVariable",
        "ForLoop",
    } & _labels(items)


@pytest.mark.parametrize(
    ("type_name", "present", "absent", "has_constants"),
    [
        (
            "int",
            {"Globals.CurrentDay", "ToInt", "Math.RandomInt", "Context.NpcTalkTarget"},
            {
                "Context.DelayedEventLabel",
                "ToString",
                "Math.RandomFloat",
                "true",
                "false",
                # Only the canonical spelling of a target is offered.
                "LovePoints",
                "NpcTalkTarget",
                "LOVE",
                "Character.Love",
                "Love",
                "CardStorage.GetInt",
            },
            True,
        ),
        (
            "float",
            {"ToFloat", "Math.RandomFloat", "ThisCard"},
            {"Globals.CurrentDay", "ToInt", "Context.DelayedEventLabel", "true", "false"},
            False,
        ),
        (
            "string",
            {"ToString", "Context.DelayedEventLabel", "Text.Replace", "ThisCard"},
            {"Globals.CurrentDay", "ToInt", "Math.RandomFloat", "true", "false"},
            False,
        ),
        # A comparison can follow, so a bool slot offers a value of every type.
        (
            "bool",
            {"Globals.AutoPc", "Globals.IsSeatFilled", "Globals.CurrentDay", "ToString", "true"},
            set(),
            True,
        ),
    ],
)
def test_value_slots_offer_names_that_fit_the_expected_type(
    context, type_name, present, absent, has_constants
):
    source = f'module "M" {{ trigger "T" {{ let result: {type_name} = '
    items = completions(source, len(source), context)
    labels = _labels(items)

    assert present <= labels
    assert not absent & labels
    assert (CompletionItemKind.Constant in {item.kind for item in items}) is has_constants


def test_zero_argument_runtime_expressions_use_property_kind_and_bare_edits(context):
    source = 'module "M" { trigger "T" { let day: int = Globals.Cur'
    item = next(
        item
        for item in completions(source, len(source), context, snippet_support=True)
        if item.label == "Globals.CurrentDay"
    )

    assert item.kind == CompletionItemKind.Property
    assert item.insert_text == "Globals.CurrentDay"
    assert item.text_edit is not None
    assert item.text_edit.new_text == "Globals.CurrentDay"


def test_protected_builtin_completes_bare_beside_a_quoted_same_named_variable(context):
    source = 'module "M" { trigger "T" { let "ThisCard": int = 1; let result: int = ThisC; } }'
    cursor = source.index("ThisC;") + len("ThisC")
    items = completions(source, cursor, context, snippet_support=True)
    builtin = next(
        item
        for item in items
        if item.label == "ThisCard" and item.kind == CompletionItemKind.Property
    )
    variable = next(
        item
        for item in items
        if item.label == "ThisCard" and item.kind == CompletionItemKind.Variable
    )
    completed = _apply_snippet_completion(source, builtin)
    analysis = analyze_source(completed, context=context)

    assert builtin.text_edit.new_text == "ThisCard"
    assert variable.text_edit.new_text == 'variable("ThisCard")'
    assert analysis.result.is_valid
    assert any(
        reference.name == "ThisCard" and reference.metadata is not None
        for reference in analysis.bound.references
    )


def test_existing_expression_call_callee_suppresses_noncallable_values(context):
    source = 'module "M" { global ToInt: int = 1; trigger "T" { let result: int = ToIn("1"); } }'
    cursor = source.index("ToIn(") + len("ToIn")
    items = completions(source, cursor, context)

    assert any(item.label == "ToInt" for item in items)
    assert not any(
        item.kind in {CompletionItemKind.Variable, CompletionItemKind.Constant} for item in items
    )
    callable_item = next(item for item in items if item.label == "ToInt")
    assert validate_source(
        _apply_snippet_completion(source, callable_item), context=context
    ).is_valid


@pytest.mark.parametrize(
    ("text", "present", "absent"),
    [
        # A boolean slot may continue with a comparison, so it offers operands of every type.
        (
            'module "M" { trigger "T" { Notification("x", Globals.|',
            {"Globals.AutoPc", "Globals.CurrentDay"},
            set(),
        ),
        # A direct `!` operand stays boolean.
        (
            'module "M" { trigger "T" { let enabled: bool = !Globals.|',
            {"Globals.AutoPc"},
            {"Globals.CurrentDay"},
        ),
        # A callee the language does not know gives no type to filter by.
        (
            'module "M" { trigger "T" { let day: int = UnknownCall(|); } }',
            {"Globals.CurrentDay"},
            set(),
        ),
        ('module "M" { trigger "T" { if Glo|', {"Globals.CurrentDay"}, set()),
        ('module "M" { trigger "T" { if Context.NpcAns|', {"Context.NpcAnswerTarget"}, set()),
        ('module "M" { trigger "T" { if (Globals.|', {"Globals.CurrentDay"}, set()),
        ('module "M" { trigger "T" { if (true && (Globals.|', {"Globals.CurrentDay"}, set()),
        ('module "M" { trigger "T" { let day: int = (Globals.Cur|', {"Globals.CurrentDay"}, set()),
    ],
)
def test_names_are_offered_in_every_grammar_state_before_a_comparison_is_typed(
    context, text, present, absent
):
    source = text.replace("|", "")
    labels = _labels(completions(source, text.index("|"), context))

    assert present <= labels
    assert not absent & labels


@pytest.mark.parametrize(
    "text",
    [
        'module "M" { trigger "T" { let day: int = Globals.CurrentDay(|); } }',
        'module "M" { trigger "T" { Notification("x", true, |); } }',
    ],
    ids=["zero-argument-expression", "excess-action-argument"],
)
def test_calls_without_a_usable_argument_slot_offer_no_values(context, text):
    source = text.replace("|", "")
    value_kinds = {
        CompletionItemKind.Function,
        CompletionItemKind.Property,
        CompletionItemKind.Constant,
        CompletionItemKind.Event,
        CompletionItemKind.Variable,
    }

    assert not any(
        item.kind in value_kinds for item in completions(source, text.index("|"), context)
    )


def test_prior_comparison_does_not_leak_across_logical_call_arguments(context):
    source = (
        'module "M" { trigger "T" { let result: string = '
        "ToString(Globals.CurrentDay > 0 && "
        'ClassStorage.GetBool("key", Globals. > 0)); } }'
    )
    cursor = source.index("Globals. >") + len("Globals.")
    items = completions(source, cursor, context)
    labels = {item.label for item in items}

    assert "Globals.CurrentDay" in labels
    assert "Globals.AutoPc" in labels
    item = next(item for item in items if item.label == "Globals.CurrentDay")
    assert validate_source(apply_text_edit(source, item), context=context).is_valid


def test_event_prefixes_are_events_and_calls_after_an_event_are_actions(context):
    event_prefix = 'module "M" { trigger "T" { on NPC_'
    event_items = completions(event_prefix, len(event_prefix), context)
    assert any(item.label.startswith("NPC_") for item in event_items)
    assert all(item.label not in {"Notification", "WriteLog"} for item in event_items)

    action_source = 'module "M" { trigger "T" { on CARD_ADDED; Noti'
    action_items = completions(action_source, len(action_source), context)
    assert "Notification" in {item.label for item in action_items}
    assert not any(item.label.startswith("CARD_") for item in action_items)


@pytest.mark.parametrize(
    ("text", "label", "completed"),
    [
        # The cursor sits inside the token: the rest of it is replaced too.
        (
            'module "M😀" { trigger "T" { let day: int = Globals.Cur|rentDay; } }',
            "Globals.CurrentDay",
            'module "M😀" { trigger "T" { let day: int = Globals.CurrentDay; } }',
        ),
        # The terminator after the name stays.
        (
            'module "M" { trigger "T" { Noti|; } }',
            "Notification",
            'module "M" { trigger "T" { Notification; } }',
        ),
        # The arguments of an existing call stay.
        (
            'module "M" { trigger "T" { No|ti("keep", true); } }',
            "Notification",
            'module "M" { trigger "T" { Notification("keep", true); } }',
        ),
    ],
)
def test_completion_replaces_the_whole_name_token_under_the_cursor(context, text, label, completed):
    source = text.replace("|", "")
    item = next(
        item for item in completions(source, text.index("|"), context) if item.label == label
    )

    assert apply_text_edit(source, item) == completed


def test_dotted_completion_items_filter_by_their_full_label(context):
    source = 'module "M" { trigger "T" { let day: int = Globals.'
    items = completions(source, len(source), context)

    assert items
    assert all(item.filter_text == item.label for item in items)
    typed = "globals.p"
    assert "Globals.PlayerCharacter" in {
        item.label for item in items if item.filter_text.casefold().startswith(typed)
    }


def _apply_snippet_completion(source, item):
    assert item.text_edit is not None
    text = re.sub(r"\$\{\d+:([^}]*)\}", r"\1", item.text_edit.new_text)
    text = text.replace("$0", "")
    start = item.text_edit.range.start.character
    end = item.text_edit.range.end.character
    return source[:start] + text + source[end:]


def test_action_snippet_keeps_existing_semicolon_and_optional_default(context):
    source = 'module "M" { trigger "T" { on CARD_ADDED; Noti; } }'
    cursor = source.index("Noti") + len("Noti")
    item = next(
        item
        for item in completions(source, cursor, context, snippet_support=True)
        if item.label == "Notification"
    )
    completed = _apply_snippet_completion(source, item)

    assert item.insert_text == 'Notification(${1:""})$0'
    assert validate_source(completed, context=context).is_valid


def test_event_completion_keeps_existing_semicolon(context):
    source = 'module "M" { trigger "T" { on CARD_AD; } }'
    cursor = source.index("CARD_AD") + len("CARD_AD")
    item = next(
        item
        for item in completions(source, cursor, context, snippet_support=True)
        if item.label == "CARD_ADDED"
    )
    completed = _apply_snippet_completion(source, item)

    assert item.kind == CompletionItemKind.Event
    assert item.text_edit is not None
    assert item.text_edit.new_text == "CARD_ADDED"
    assert validate_source(completed, context=context).is_valid


def test_scope_and_expected_type_filter_global_local_and_loop_names(context):
    source = (
        'module "M" { global Shared: int = 0; global Enabled: bool = false; '
        'trigger "T" { let Local: int = 1; loop { if Local > 0 { break if false; } } '
        "let result: int = Local; } }"
    )
    analysis = analyze_source(source, context=context)
    cursor = source.index("= Local", source.index("let result")) + 2
    items = completions(source, cursor, context, analysis=analysis)
    labels = {item.label for item in items}

    assert {"Shared", "Local"} <= labels
    assert "Enabled" not in labels

    break_cursor = source.index("break if false") + len("break if ")
    break_items = completions(source, break_cursor, context, analysis=analysis)
    break_labels = {item.label for item in break_items}
    assert "Globals.AutoPc" in break_labels


def test_global_initializers_offer_literals_but_no_runtime_expressions(context):
    source = 'module "M" { global value: bool = '
    items = completions(source, len(source), context)

    assert {"true", "false"} <= {item.label for item in items}
    assert not any(
        item.kind
        in {
            CompletionItemKind.Function,
            CompletionItemKind.Property,
            CompletionItemKind.Constant,
            CompletionItemKind.Event,
        }
        for item in items
    )


def test_assignment_statement_starts_offer_visible_variable_targets(context):
    source = (
        'module "M" { global Shared: int = 0; trigger "T" { let Local: int = 1; Shared = 2; } }'
    )
    analysis = analyze_source(source, context=context)
    cursor = source.rindex("Shared =")
    items = completions(source, cursor, context, analysis=analysis)
    variable_items = {item.label for item in items if item.kind == CompletionItemKind.Variable}

    assert {"Shared", "Local"} <= variable_items


def test_declaration_type_slot_offers_the_value_types(context):
    source = 'module "M" { trigger "T" { let value: '
    labels = _labels(completions(source, len(source), context))

    assert {"int", "bool", "float", "string"} <= labels


def test_completion_recovers_after_an_earlier_unfinished_statement(context):
    source = 'module "M" { trigger "T" { if (true &&\n  break\n  Noti'
    labels = {item.label for item in completions(source, len(source), context)}

    assert "Notification" in labels


def test_imported_authored_macro_remains_available_in_module_statements(tmp_path):
    library = tmp_path / "library.aa2mi"
    library.write_text(
        'macro "write" { param message string; WriteLog(message); }\n',
        encoding="utf-8",
    )
    context = SourceContext.create(filename=str(tmp_path / "module.aa2m"), import_base=tmp_path)
    source = 'import "library.aa2mi"; module "M" { trigger "T" { write'
    analysis = analyze_source(source, context=context)
    items = completions(source, len(source), context, analysis=analysis)

    assert any(item.label.casefold() == "write".casefold() for item in items)
