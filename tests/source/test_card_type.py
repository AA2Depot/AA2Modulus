"""The source-only card type checks seat positions while preserving native int records."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import compile_source, validate_source
from aa2modulus.app.decompile import decompile_module
from tests.support.source import module_source, parse_module


def _errors(source: str, **options):
    return validate_source(source, filename="card.aa2m", **options).errors


def test_swapped_member_arguments_report_card_type_and_exact_cast_fix():
    source = module_source(
        "let coach: card = ThisCard; let amount: int = 30; coach.AddLike(amount, coach);"
    )

    (error,) = _errors(source)
    assert error.code == "SOURCE_TYPE_MISMATCH"
    assert error.message == "expected card, found int"
    assert error.help is not None
    assert "source type int" in error.help
    assert "declare seat variables as card" in error.help
    (fix,) = error.fixes
    assert fix.replacement == "Card(amount)"
    fixed = source.replace("coach.AddLike(amount, coach)", "coach.AddLike(Card(amount), coach)")
    assert _errors(fixed) == ()


def test_card_positions_accept_literals_constants_and_explicit_casts():
    source = module_source(
        "let coach: card = ThisCard; let seat: card = ((4)); "
        'coach.AddLike(Seat, 1); coach.AddLike(Card(const("With Spaces")), 2);',
        'const Seat: int = 3; const "With Spaces": int = 5;',
    )
    literal = module_source(
        "let coach: card = ThisCard; let seat: card = ((4)); "
        "coach.AddLike(3, 1); coach.AddLike(5, 2);"
    )
    assert compile_source(source) == compile_source(literal)


def test_card_placeholder_can_be_assigned_conditionally_without_a_range_check():
    source = module_source(
        "let trainee: card = 25; "
        "if ThisCard == TriggeringCard { trainee = TriggeringCard; } "
        "trainee.SetVirtue(1);"
    )
    native = module_source(
        "let trainee: int = 25; "
        "if ThisCard == TriggeringCard { trainee = TriggeringCard; } "
        "raw_action 32(trainee, 1);"
    )
    assert validate_source(source).diagnostics == ()
    assert compile_source(source) == compile_source(native)


def test_card_widens_for_int_parameters_arithmetic_and_ordering_but_not_equality():
    accepted = module_source(
        "let coach: card = ThisCard; let n: int = 2; "
        'coach.SetInt("seat", coach); let sum: int = coach + n; '
        "if coach < n { coach.SetVirtue(1); } "
        "if coach == -1 { coach.SetVirtue(2); }"
    )
    assert _errors(accepted) == ()

    rejected = module_source("let coach: card = ThisCard; let seat: int = 2; if coach == seat {}")
    (error,) = _errors(rejected)
    assert error.code == "SOURCE_TYPE_MISMATCH"
    assert error.message == "expected card, found int"
    assert error.fixes[0].replacement == "Card(seat)"


def test_flat_card_parameter_roles_and_card_for_start_are_checked():
    accepted = module_source(
        "let seat: card = ThisCard; let other: card = 0; "
        "if Globals.IsSeatFilled(seat) {} "
        "for other from seat to 24 { other.SetVirtue(1); }"
    )
    assert _errors(accepted) == ()

    rejected = module_source(
        "let seat: int = 1; let other: card = 0; if Globals.IsSeatFilled(seat) {} "
        "for other from seat to 24 {}"
    )
    errors = _errors(rejected)
    assert [error.code for error in errors] == [
        "SOURCE_TYPE_MISMATCH",
        "SOURCE_TYPE_MISMATCH",
    ]
    assert [error.fixes[0].replacement for error in errors] == [
        "Card(seat)",
        "Card(seat)",
    ]


def test_macro_formals_and_template_slots_can_carry_card_values(tmp_path):
    macro = (
        'macro "like" { param who card; param towards card; '
        "who.AddLike(towards, 1); }\n" + module_source("like(ThisCard, TriggeringCard);")
    )
    assert _errors(macro) == ()

    (tmp_path / "lib.aa2mi").write_text(
        'trigger "Apply" { slot who card; slot towards card; on CARD_ADDED; '
        "who.AddLike(towards, 1); }",
        encoding="utf-8",
    )
    imported = (
        'import "lib.aa2mi"; module "M" { '
        'import.trigger "Apply" { slot who = ThisCard; slot towards = 3; } }'
    )
    assert _errors(imported, import_base=tmp_path) == ()

    bad_macro = 'macro "like" { param who card; who.AddLike(1, 1); }\n' + module_source(
        "let amount: int = 3; like(amount);"
    )
    (macro_error,) = _errors(bad_macro)
    assert macro_error.code == "SOURCE_TYPE_MISMATCH"
    assert macro_error.fixes[0].replacement == "Card(amount)"

    bad_imported = (
        'import "lib.aa2mi"; module "M" { global amount: int = 3; '
        'import.trigger "Apply" { slot who = amount; slot towards = 3; } }'
    )
    slot_errors = _errors(bad_imported, import_base=tmp_path)
    assert [(error.code, error.message) for error in slot_errors] == [
        ("SOURCE_TYPE_MISMATCH", "expected card, found int")
    ]
    assert slot_errors[0].fixes[0].replacement == "Card(amount)"


def test_card_globals_lower_to_native_int_without_card_in_ir():
    card_global = 'module "M" { global selected: card { default 2; current 3; initialized true; } }'
    int_global = 'module "M" { global selected: int { default 2; current 3; initialized true; } }'
    card_module = parse_module(card_global)
    int_module = parse_module(int_global)

    assert compile_source(card_global) == compile_source(int_global)
    assert card_module.to_ir() == int_module.to_ir()
    assert card_module.to_ir()["globals"][0]["type"] == 1
    assert "card" not in repr(card_module.to_ir()).casefold()


def test_raw_int_expression_needs_explicit_card_conversion_in_member_position():
    raw = 'raw_expression int 2 { variable "seat"; }'
    unconverted = module_source(
        f"let coach: card = ThisCard; let seat: int = 3; coach.AddLike({raw}, 1);"
    )
    (error,) = _errors(unconverted)
    assert error.code == "SOURCE_TYPE_MISMATCH"
    assert error.message == "expected card, found int"

    source = module_source(
        f"let coach: card = ThisCard; let seat: int = 3; coach.AddLike(Card({raw}), 1);"
    )
    assert _errors(source) == ()


@pytest.mark.parametrize(
    ("value", "found"), [("true", "bool"), ("1.5", "float"), ('"seat"', "string")]
)
def test_card_conversion_rejects_non_int_values(value, found):
    (error,) = _errors(module_source(f"let seat: card = Card({value});"))
    assert error.code == "SOURCE_TYPE_MISMATCH"
    assert error.message == f"expected int, found {found}"


def test_arithmetic_result_is_int_and_requires_card_conversion_at_card_position():
    source = module_source(
        "let coach: card = ThisCard; let seat: int = 2; coach.AddLike(seat + 1, 1);"
    )
    (error,) = _errors(source)
    assert error.code == "SOURCE_TYPE_MISMATCH"
    assert error.message == "expected card, found int"
    assert error.fixes[0].replacement == "Card(seat + 1)"


def test_card_declarations_accept_card_casts_for_initializer_assignment_and_loop_start():
    card_source = module_source(
        "let seed: int = 2; let seat: card = Card(seed); seat = Card(seed); "
        "for seat from Card(seed) to 4 {}"
    )
    int_source = module_source(
        "let seed: int = 2; let seat: int = seed; seat = seed; for seat from seed to 4 {}"
    )
    assert _errors(card_source) == ()
    assert compile_source(card_source) == compile_source(int_source)


def test_quoted_card_keyword_names_remain_recoverable():
    source = module_source('let "Card": card = ThisCard; variable("Card").SetVirtue(1);')
    binary = compile_source(source)
    recovered = decompile_module(binary).source
    assert 'let "Card": card' in recovered
    assert 'variable("Card").SetVirtue(1);' in recovered
    assert compile_source(recovered) == binary


def test_decompiler_infers_card_locals_and_recompiles_byte_identically():
    card_only = module_source("let coach: card = ThisCard; coach.AddLike(3, 1);")
    card_binary = compile_source(card_only)
    card_text = decompile_module(card_binary).source
    assert "let coach: card" in card_text
    assert compile_source(card_text) == card_binary


def test_decompiler_keeps_int_when_non_card_writes_outnumber_card_uses():
    source = module_source(
        "let seat: int = 0; let n: int = 1; "
        "seat = n + 1; seat = n + 2; seat = n + 3; "
        "Card(seat).AddLike(1, 1); if Card(seat) == ThisCard {}"
    )
    binary = compile_source(source)
    recovered = decompile_module(binary).source

    assert "let seat: int" in recovered
    assert "Card(seat).AddLike" in recovered
    assert "Card(seat) == ThisCard" in recovered
    assert compile_source(recovered) == binary


def test_decompiler_chooses_card_when_card_uses_outnumber_non_card_writes():
    source = module_source(
        "let seed: int = 1; let seat: int = seed; seat = seed; "
        "for seat from seed to 4 { "
        "Card(seat).AddLike(1, 1); Card(seat).AddLike(2, 2); "
        "Card(seat).AddLike(3, 3); if Card(seat) == ThisCard {} }"
    )
    binary = compile_source(source)
    recovered = decompile_module(binary).source

    assert "let seat: card = Card(seed);" in recovered
    assert "seat = Card(seed);" in recovered
    assert "for seat from Card(seed) to 4" in recovered
    assert "seat.AddLike" in recovered
    assert compile_source(recovered) == binary
