"""Broad completion inventory checks against the source policy and binder."""

from __future__ import annotations

import json
import re

import pytest
from lsprotocol.types import CompletionItemKind

from aa2modulus.app.compile import validate_source
from aa2modulus.context.operation import SourceContext
from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.metadata.identities import WireIdentity
from aa2modulus.model.native import (
    ActionMetadata,
    EventMetadata,
    ExpressionMetadata,
    NamedConstantMetadata,
)
from aa2modulus.pipeline.analysis import analyze_source


@pytest.mark.parametrize("name", ["true", "name.with.dot", 'two words "quoted" 😀'])
@pytest.mark.parametrize("statement", [False, True])
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


def _source_spellings(context, entry, kind: str) -> tuple[str, ...]:
    """List only flat source forms the catalog proves can select this wire target.

    Member forms are written after a receiver, so they are never flat completion labels.
    """

    if kind == "action" and isinstance(entry, ActionMetadata):
        wire = WireIdentity("action", entry.id)
    elif kind == "event" and isinstance(entry, EventMetadata):
        wire = WireIdentity("event", entry.id)
    elif kind == "expression" and isinstance(entry, ExpressionMetadata):
        wire = WireIdentity("expression", entry.id, entry.return_type)
    elif kind == "named_constant" and isinstance(entry, NamedConstantMetadata):
        wire = WireIdentity("named_constant", entry.id, entry.value_type)
    else:
        return ()
    target = context.catalog.native_targets.get(wire)
    if target is None:
        return ()
    return tuple(
        form.spelling for form in target.forms if form.reversible and form.kind != "member"
    )


def _labels(items, kind):
    return {item.label for item in items if item.kind == kind}


def _folded(values):
    return {value.casefold() for value in values}


def test_policy_visible_event_inventory_is_available_after_on(context):
    source = 'module "M" { trigger "T" { on '
    items = completions(source, len(source), context)
    expected = {
        name
        for entry in context.metadata.events
        for name in _source_spellings(context, entry, "event")
    }
    action_names = {
        name
        for entry in context.metadata.actions
        for name in _source_spellings(context, entry, "action")
    }

    assert expected <= _labels(items, CompletionItemKind.Event)
    assert not (action_names - expected) & {item.label for item in items}


def test_policy_visible_action_inventory_is_available_in_statement_position(context):
    source = 'module "M" { trigger "T" { on CARD_ADDED; '
    items = completions(source, len(source), context)
    expected = {
        name
        for entry in context.metadata.actions
        for name in _source_spellings(context, entry, "action")
    }

    assert expected <= _labels(items, CompletionItemKind.Function)
    assert "CARD_ADDED" not in {item.label for item in items}
    action_labels = _labels(items, CompletionItemKind.Function)
    assert not {"AddLike", "SetVirtue", "Character.AddLike", "CardStorage.SetInt"} & action_labels
    assert "SetVariable" not in action_labels
    assert "ForLoop" not in action_labels
    statement_start = 'module "M" { trigger "T" { '
    keywords = _labels(
        completions(statement_start, len(statement_start), context), CompletionItemKind.Keyword
    )
    assert {"for", "if", "loop"} <= keywords


@pytest.mark.parametrize(
    "type_name,value_type", [("int", 1), ("bool", 2), ("float", 3), ("string", 4)]
)
def test_expression_and_constant_inventory_obeys_expected_type(context, type_name, value_type):
    source = f'module "M" {{ trigger "T" {{ let result: {type_name} = '
    items = completions(source, len(source), context)
    expected_expressions = {
        name
        for entry in context.metadata.expressions
        if entry.return_type in ((1, 2, 3, 4) if value_type == 2 else (value_type,))
        for name in _source_spellings(context, entry, "expression")
    }
    # Card receivers fit every value slot through a member.
    expected_expressions.update(
        name
        for entry in context.metadata.expressions
        if context.source_policy.expression_result_role(entry.return_type, entry.id) == "card"
        for name in _source_spellings(context, entry, "expression")
    )
    expected_constants = {
        name
        for entry in context.metadata.named_constants
        if entry.value_type in ((1, 2, 3, 4) if value_type == 2 else (value_type,))
        for name in _source_spellings(context, entry, "named_constant")
    }
    expected_constants.update(
        value.name
        for value in context.catalog.source_values
        if value.value_type in ((1, 2, 3, 4) if value_type == 2 else (value_type,))
    )
    actual_expressions = _labels(items, CompletionItemKind.Function) | _labels(
        items, CompletionItemKind.Property
    )
    actual_constants = _labels(items, CompletionItemKind.Constant)
    assert _folded(expected_expressions) <= _folded(actual_expressions)
    assert _folded(expected_constants) <= _folded(actual_constants)
    assert _folded(actual_expressions) <= _folded(expected_expressions)
    assert _folded(actual_constants) <= _folded(expected_constants)


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


@pytest.mark.parametrize("type_name", ["int", "float", "string"])
def test_known_nonboolean_value_slot_does_not_offer_boolean_literals(context, type_name):
    source = f'module "M" {{ trigger "T" {{ let result: {type_name} = '
    items = completions(source, len(source), context)

    assert not any(item.label in {"true", "false"} for item in items)


def test_bool_call_arguments_allow_future_comparison_operands(context):
    source = 'module "M" { trigger "T" { Notification("x", Globals.'
    labels = {item.label for item in completions(source, len(source), context)}

    assert "Globals.AutoPc" in labels
    assert "Globals.CurrentDay" in labels


def test_direct_not_operand_remains_bool_filtered(context):
    source = 'module "M" { trigger "T" { let enabled: bool = !Globals.'
    labels = {item.label for item in completions(source, len(source), context)}

    assert "Globals.AutoPc" in labels
    assert "Globals.CurrentDay" not in labels


def test_known_zero_argument_expression_has_no_argument_completions(context):
    source = 'module "M" { trigger "T" { let day: int = Globals.CurrentDay(); } }'
    cursor = source.index("Globals.CurrentDay(") + len("Globals.CurrentDay(")
    items = completions(source, cursor, context)
    value_kinds = {
        CompletionItemKind.Function,
        CompletionItemKind.Property,
        CompletionItemKind.Constant,
        CompletionItemKind.Event,
        CompletionItemKind.Variable,
    }

    assert not any(item.kind in value_kinds for item in items)


def test_excess_action_argument_has_no_value_completions(context):
    source = 'module "M" { trigger "T" { Notification("x", true, ); } }'
    cursor = source.index("true,") + len("true,") + 1
    items = completions(source, cursor, context)
    value_kinds = {
        CompletionItemKind.Function,
        CompletionItemKind.Property,
        CompletionItemKind.Constant,
        CompletionItemKind.Event,
        CompletionItemKind.Variable,
    }

    assert not any(item.kind in value_kinds for item in items)


def test_unknown_call_without_signature_still_offers_useful_values(context):
    source = 'module "M" { trigger "T" { let day: int = UnknownCall(); } }'
    cursor = source.index("UnknownCall(") + len("UnknownCall(")
    labels = {item.label for item in completions(source, cursor, context)}

    assert "Globals.CurrentDay" in labels


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
    assert item.text_edit is not None
    codec = PositionCodec(source, encoding="utf-16")
    begin = codec.offset(item.text_edit.range.start)
    end = codec.offset(item.text_edit.range.end)
    completed = source[:begin] + item.text_edit.new_text + source[end:]
    assert validate_source(completed, context=context).is_valid


def test_event_prefixes_are_events_and_calls_after_an_event_are_actions(context):
    event_prefix = 'module "M" { trigger "T" { on NPC_'
    event_items = completions(event_prefix, len(event_prefix), context)
    assert any(item.label.startswith("NPC_") for item in event_items)
    assert all(item.label not in {"Notification", "WriteLog"} for item in event_items)

    action_source = 'module "M" { trigger "T" { on CARD_ADDED; Noti'
    action_items = completions(action_source, len(action_source), context)
    assert "Notification" in {item.label for item in action_items}
    assert not any(item.label.startswith("CARD_") for item in action_items)


def test_completion_edit_preserves_a_following_statement_semicolon(context):
    source = 'module "M" { trigger "T" { Noti; } }'
    start = source.index("Noti")
    cursor = start + len("Noti")
    item = next(
        item for item in completions(source, cursor, context) if item.label == "Notification"
    )

    assert item.text_edit is not None
    begin, end = item.text_edit.range.start.character, item.text_edit.range.end.character
    completed = source[:begin] + item.text_edit.new_text + source[end:]
    assert completed == source.replace("Noti;", "Notification;")


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


@pytest.mark.parametrize(
    ("fragment", "expected"),
    [
        ("if Glo", "Globals.CurrentDay"),
        ("if Context.NpcAns", "Context.NpcAnswerTarget"),
    ],
)
def test_unfinished_condition_preserves_future_comparison_operands(context, fragment, expected):
    source = f'module "M" {{ trigger "T" {{ {fragment}'
    labels = {item.label for item in completions(source, len(source), context)}

    assert expected in labels


@pytest.mark.parametrize(
    "source",
    [
        'module "M" { trigger "T" { if (Globals.',
        'module "M" { trigger "T" { if (true && (Globals.',
    ],
)
def test_incomplete_grouped_condition_offers_comparison_member_names(context, source):
    labels = {item.label for item in completions(source, len(source), context)}

    assert "Globals.CurrentDay" in labels


def test_parenthesized_expression_and_declaration_type_slots(context):
    expression = 'module "M" { trigger "T" { let day: int = (Globals.Cur'
    expression_labels = {item.label for item in completions(expression, len(expression), context)}
    type_slot = 'module "M" { trigger "T" { let value: '
    type_labels = {item.label for item in completions(type_slot, len(type_slot), context)}
    bool_group = 'module "M" { trigger "T" { let ok: bool = (Globals.'
    bool_group_labels = {item.label for item in completions(bool_group, len(bool_group), context)}

    assert "Globals.CurrentDay" in expression_labels
    assert "Globals.CurrentDay" in bool_group_labels
    assert {"int", "bool", "float", "string"} <= type_labels


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
