"""Receiver-call source forms lower to the expected native records."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import compile_source, parse_and_validate_source
from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.decompile.format.module import format_module
from aa2modulus.metadata.loader import load_metadata
from aa2modulus.model.records import (
    ActionCall,
    Event,
    Expression,
    GuiAction,
    Module,
    Trigger,
    Variable,
)
from aa2modulus.model.types import EXPR_CONSTANT, EXPR_VAR, ValueType
from aa2modulus.model.values import Value
from aa2modulus.semantics.binding.state import SourceBindingError
from tests.support.source import parse_module

ACTION_ADD_LIKE = 13


def _module(body: str, *, prefix: str = "") -> str:
    return f'{prefix}module "M" {{ trigger "T" {{ on CARD_ADDED; {body} }} }}'


def _codes(source: str, **kwargs) -> list[str]:
    _, result = parse_and_validate_source(source, **kwargs)
    return [item.code for item in result.diagnostics]


def _bind_error(source: str, **kwargs) -> SourceBindingError:
    with pytest.raises(SourceBindingError) as raised:
        parse_module(source, **kwargs)
    return raised.value


def _first_action_arguments(module: Module) -> tuple[Expression, ...]:
    action = module.triggers[0].gui_actions[0].action
    assert isinstance(action, ActionCall) and action.id == ACTION_ADD_LIKE
    return action.parameters


def test_member_action_matches_hand_authored_native_records_and_rejects_flat_spelling():
    member = _module("let actor: card = ThisCard; actor.AddLike(Context.NpcTalkTarget, 30);")
    flat = _module(
        "let actor: card = ThisCard; Character.AddLike(actor, Context.NpcTalkTarget, 30);"
    )
    expected = Module(
        "M",
        triggers=(
            Trigger(
                "T",
                events=(Event(6),),
                variables=(Variable(ValueType.INT, "actor", Expression(ValueType.INT, 10)),),
                gui_actions=(
                    GuiAction(
                        ActionCall(
                            ACTION_ADD_LIKE,
                            (
                                Expression(ValueType.INT, EXPR_VAR, variable_name="actor"),
                                Expression(ValueType.INT, 15),
                                Expression(
                                    ValueType.INT, EXPR_CONSTANT, constant=Value.integer(30)
                                ),
                            ),
                        )
                    ),
                ),
            ),
        ),
    )

    assert parse_module(member) == expected
    assert compile_source(member) == encode_module(expected)
    error = _bind_error(flat)
    assert error.diagnostic.code == "UNKNOWN_ACTION_NAME"
    assert "use 'actor.AddLike(Context.NpcTalkTarget, 30)'" in error.diagnostic.help


def test_card_property_receiver_uses_slot_zero_and_formats_without_call_parens():
    source = _module("let actor: card = ThisCard; let virtue: int = actor.Virtue;")
    module = parse_module(source)
    expression = module.triggers[0].variables[1].default_expression
    assert expression.return_type is ValueType.INT
    assert expression.id == 25  # Native INT/25 is the Virtue getter.
    assert (expression.parameters[0].id, expression.parameters[0].variable_name) == (2, "actor")
    formatted = format_module(module)
    assert "let virtue: int = actor.Virtue;" in formatted
    assert "actor.Virtue()" not in formatted
    assert compile_source(formatted) == compile_source(source)


@pytest.mark.parametrize(
    "receiver",
    ["actor.AddLike", "(actor).AddLike", 'variable("actor").AddLike', "actor.addlike"],
)
def test_every_receiver_syntax_selects_the_same_native_action(receiver):
    baseline = _module("let actor: card = ThisCard; actor.AddLike(7, -3);")
    member = _module(f"let actor: card = ThisCard; {receiver}(7, -3);")

    assert compile_source(member) == compile_source(baseline)


def test_negative_and_computed_amounts_keep_signed_native_values():
    source = _module(
        "let actor: card = ThisCard; actor.AddLike(Context.NpcTalkTarget, 0 - 2147483647 - 1);",
    )
    arguments = _first_action_arguments(parse_module(source))

    assert [item.id for item in arguments] == [EXPR_VAR, 15, arguments[2].id]
    assert arguments[2].parameters  # a computed subtraction, not a folded literal
    folded = _module(
        "let actor: card = ThisCard; actor.AddLike(Context.NpcTalkTarget, -2147483648);"
    )
    assert compile_source(source) != compile_source(folded)


def test_nontrivial_receiver_and_arguments_appear_once_in_native_order():
    source = _module(
        'Card(ThisCard.GetInt("who", 0)).AddLike(Card(ThisCard.GetInt("t", 0)), 1);',
    )
    # Call results are valid explicit receivers only through the postfix grammar.
    arguments = _first_action_arguments(parse_module(source))
    getter = load_metadata().expression(ValueType.INT, arguments[0].id)

    assert [item.id for item in arguments] == [24, 24, EXPR_CONSTANT]
    assert getter is not None and getter.parameter_types[0] == ValueType.INT
    assert arguments[0].parameters[1].constant == Value.string("who")
    assert arguments[1].parameters[1].constant == Value.string("t")
    parenthesized = _module(
        '(Card(ThisCard.GetInt("who", 0))).AddLike(Card(ThisCard.GetInt("t", 0)), 1);'
    )
    assert compile_source(source) == compile_source(parenthesized)


def test_receiver_is_bound_once_and_not_copied_when_the_formal_is_used_twice():
    source = _module(
        'let actor: card = ThisCard; (Card(actor.GetInt("n", 0))).AddLike(1, 2);',
    )
    arguments = _first_action_arguments(parse_module(source))

    assert sum(item.id == 24 for item in arguments) == 1
    assert len(arguments) == 3


def test_macro_and_template_receivers_follow_existing_substitution_semantics(tmp_path):
    macro = (
        'macro "like" { param "who" card; param "amount" int; who.AddLike(who, amount); }\n'
        + _module('let actor: card = ThisCard; like(Card(actor.GetInt("n", 0)), 5);')
    )
    expanded = _module(
        'let actor: card = ThisCard; Card(actor.GetInt("n", 0)).AddLike(Card(actor.GetInt("n", '
        "0)), 5);"
    )
    # The formal receiver appears twice, so its actual is evaluated twice (as flat calls do).
    assert compile_source(macro) == compile_source(expanded)

    (tmp_path / "lib.aa2mi").write_text(
        'trigger "T" { slot "who" card; on CARD_ADDED; who.AddLike(who, 4); }', encoding="utf-8"
    )
    imported = 'import "lib.aa2mi"; module "M" { import.trigger "T" { slot "who" = ThisCard; } }'
    expanded = _module("ThisCard.AddLike(ThisCard, 4);")
    assert compile_source(imported, import_base=tmp_path) == compile_source(expanded)


def test_templates_and_macros_cannot_capture_variables_through_a_receiver(tmp_path):
    macro = 'macro "like" { param "amount" int; actor.AddLike(1, amount); }\n' + _module(
        "let actor: card = ThisCard; like(2);"
    )
    assert "UNKNOWN_ACTION_NAME" in _codes(macro)

    (tmp_path / "lib.aa2mi").write_text(
        'trigger "T" { slot "who" card; on CARD_ADDED; outsider.AddLike(1, 2); }', encoding="utf-8"
    )
    imported = 'import "lib.aa2mi"; module "M" { import.trigger "T" { slot "who" = ThisCard; } }'
    assert "UNKNOWN_ACTION_NAME" in _codes(imported, import_base=tmp_path)


@pytest.mark.parametrize(
    ("body", "code"),
    (
        ('let actor: string = "x"; actor.AddLike(1, 2);', "SOURCE_TYPE_MISMATCH"),
        ("let actor: card = ThisCard; actor.AddLike(1);", "MEMBER_ARITY"),
        ("let actor: card = ThisCard; actor.Unknown(1, 2);", "UNKNOWN_MEMBER"),
        ("let actor: card = ThisCard; let x: int = actor.AddLike(1, 2);", "MEMBER_KIND"),
        ("let actor: card = ThisCard; actor.Virtue;", "MEMBER_KIND"),
        ("ThisCard.FullName;", "MEMBER_KIND"),
        ("Conversation.Actor(0).Virtue;", "MEMBER_KIND"),
        ("let actor: card = ThisCard; actor.AddLike(1, 2) { }", "MEMBER_ACTION_BLOCK"),
        ("nobody.AddLike(1, 2);", "UNKNOWN_ACTION_NAME"),
    ),
)
def test_receiver_diagnostics_are_specific(body, code):
    assert _codes(_module(body)) == [code]


def test_variable_case_is_exact_for_receivers_but_members_are_case_insensitive():
    source = _module(
        "let actor: card = ThisCard; let Actor: card = Context.NpcTalkTarget; "
        "actor.addlike(1, 2); Actor.ADDLIKE(3, 4);"
    )
    exact = _module(
        "let actor: card = ThisCard; let Actor: card = Context.NpcTalkTarget; "
        'variable("actor").AddLike(1, 2); variable("Actor").AddLike(3, 4);'
    )

    assert compile_source(source) == compile_source(exact)


def test_registered_namespaces_win_and_explicit_forms_select_same_named_variables():
    shadowed = _module(
        "let Context: card = ThisCard; let context: card = Context.NpcTalkTarget; "
        "let who: int = Context.npctalktarget;"
    )
    # A variable named like a namespace never retargets the registered static name.
    assert parse_module(shadowed).triggers[0].variables[2].default_expression == (
        parse_module(
            _module(
                "let Context: card = ThisCard; let context: card = Context.NpcTalkTarget; "
                "let who: int = Context.NpcTalkTarget;"
            )
        )
        .triggers[0]
        .variables[2]
        .default_expression
    )
    unknown = _module("let Context: card = ThisCard; Context.AddLike(1, 2);")
    assert "UNKNOWN_ACTION_NAME" in _codes(unknown)
    unknown_static = _module("let Context: card = ThisCard; Context.Unknown(1, 2);")
    assert "UNKNOWN_ACTION_NAME" in _codes(unknown_static)

    escaped = _module(
        'let Context: card = ThisCard; variable("Context").AddLike(1, 2); (Context).AddLike(3, 4);'
    )
    expected = Module(
        "M",
        triggers=(
            Trigger(
                "T",
                events=(Event(6),),
                variables=(Variable(ValueType.INT, "Context", Expression(ValueType.INT, 10)),),
                gui_actions=tuple(
                    GuiAction(
                        ActionCall(
                            ACTION_ADD_LIKE,
                            (
                                Expression(ValueType.INT, EXPR_VAR, variable_name="Context"),
                                *(
                                    Expression(
                                        ValueType.INT, EXPR_CONSTANT, constant=Value.integer(n)
                                    )
                                    for n in pair
                                ),
                            ),
                        )
                    )
                    for pair in ((1, 2), (3, 4))
                ),
            ),
        ),
    )
    assert parse_module(escaped) == expected


def test_quoted_dotted_variable_names_are_never_split_into_paths():
    source = _module('let "a.b": card = ThisCard; variable("a.b").AddLike(1, 2);')
    parenthesized = _module('let "a.b": card = ThisCard; (variable("a.b")).AddLike(1, 2);')

    assert compile_source(source) == compile_source(parenthesized)


def test_decompilation_and_formatting_write_member_form_and_are_byte_reversible():
    source = _module("let actor: card = ThisCard; actor.AddLike(Context.NpcTalkTarget, 30);")
    binary = compile_source(source)
    text = format_module(decode_module(binary).module)

    assert "actor.AddLike(Context.NpcTalkTarget, 30)" in text and "Character." not in text
    assert compile_source(text) == binary
