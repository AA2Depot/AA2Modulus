"""ThisCard and TriggeringCard always mean the built-in; native variables use quoted names."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import compile_source, validate_source
from aa2modulus.app.decompile import decompile_module
from aa2modulus.decompile.format.module import format_module
from aa2modulus.semantics.binding.state import SourceBindingError
from aa2modulus.syntax.parser.errors import SourceParseError
from tests.support.source import parse_module


def _code(source: str) -> str:
    result = validate_source(source)
    assert result.errors, source
    return result.errors[0].code


def _module(body: str, items: str = "") -> str:
    return f'module "M" {{ {items} trigger "T" {{ on CARD_ADDED; {body} }} }}'


NAMES = ["ThisCard", "thiscard", "THISCARD", "TriggeringCard", "triggeringcard"]


@pytest.mark.parametrize("name", NAMES)
def test_bare_global_and_local_declarations_are_rejected(name):
    assert _code(_module("", f"global {name}: int = 0;")) == "PROTECTED_NAME"
    assert _code(_module(f"let {name}: int = 0;")) == "PROTECTED_NAME"


def test_diagnostic_message_explains_the_quoted_form():
    diagnostic = validate_source(_module("let ThisCard: int = 0;")).errors[0]
    assert diagnostic.message == "'ThisCard' is a protected built-in name"
    assert diagnostic.help == (
        'quote the declaration ("ThisCard") and reference it with variable("ThisCard") '
        "to name a native variable"
    )


@pytest.mark.parametrize("name", ["ThisCard", "triggeringcard"])
def test_constants_are_rejected_even_when_quoted(name):
    for spelling in (name, f'"{name}"'):
        assert _code(_module("", f"const {spelling}: int = 1;")) == "PROTECTED_NAME"


@pytest.mark.parametrize("name", ["ThisCard", "triggeringcard"])
def test_macro_formals_are_rejected_even_when_quoted(name):
    for spelling in (name, f'"{name}"'):
        source = f'macro "m" {{ param {spelling} int; WriteLog("x"); }} ' + _module("m(1);")
        assert _code(source) == "PROTECTED_NAME"


@pytest.mark.parametrize("name", ["ThisCard", "triggeringcard"])
def test_template_slots_are_rejected_even_when_quoted(name, tmp_path):
    for spelling in (name, f'"{name}"'):
        (tmp_path / "lib.aa2mi").write_text(
            f'trigger "T" {{ slot {spelling} int; on CARD_ADDED; WriteLog("x"); }}'
        )
        result = validate_source(
            'import "lib.aa2mi"; module "M" { }', import_base=tmp_path, filename="m.aa2m"
        )
        assert result.errors[0].code == "PROTECTED_NAME"


def test_bare_loop_variable_and_assignment_target_are_rejected():
    assert _code(_module('let "ThisCard": int = 0; for ThisCard from 0 to 3 {}')) == (
        "PROTECTED_NAME"
    )
    assert _code(_module('let "ThisCard": int = 0; ThisCard = 1;')) == "PROTECTED_NAME"


def test_quoted_variable_declaration_compiles_and_is_reached_through_variable():
    source = _module(
        'let "ThisCard": int = 7; variable("ThisCard") = 8; '
        'for "ThisCard" from 0 to 2 {} ClassStorage.SetInt("k", variable("ThisCard"));',
        'global "TriggeringCard": int = 1;',
    )
    assert validate_source(source).errors == ()
    assert compile_source(source)


def test_bare_reference_binds_to_the_builtin_despite_a_quoted_variable():
    with_variable = _module(
        'let "ThisCard": int = 7; ClassStorage.SetInt("k", ThisCard);'
        ' ClassStorage.SetInt("j", thiscard);'
    )
    without = _module('ClassStorage.SetInt("k", ThisCard); ClassStorage.SetInt("j", thiscard);')
    bare = parse_module(with_variable).to_ir()["triggers"][0]["gui_actions"]
    assert bare == parse_module(without).to_ir()["triggers"][0]["gui_actions"]
    assert 'variable("ThisCard")' not in format_module(parse_module(without))


def test_explicit_call_and_receiver_forms_use_the_builtin():
    declared = 'let "ThisCard": int = 7; let "TriggeringCard": int = 8; '
    uses = (
        "WriteLog(ThisCard().FullName); ThisCard.SetVirtue(3); WriteLog(thiscard.FullName); "
        "TriggeringCard.AddLike(ThisCard, 5);"
    )
    shadowed = parse_module(_module(declared + uses))
    plain = parse_module(_module(uses))
    assert (
        shadowed.to_ir()["triggers"][0]["gui_actions"]
        == (plain.to_ir()["triggers"][0]["gui_actions"])
    )
    assert compile_source(_module(declared + uses)) is not None


def test_formatter_round_trip_quotes_protected_variables():
    source = _module(
        'let "ThisCard": int = 7; variable("ThisCard") = ThisCard; '
        'ClassStorage.SetInt("k", variable("ThisCard")); WriteLog(ThisCard.FullName);',
        'global "TriggeringCard": int = 1;',
    )
    binary = compile_source(source)
    formatted = format_module(parse_module(source))
    assert 'global "TriggeringCard": int = 1;' in formatted
    assert 'let "ThisCard": int = 7;' in formatted
    assert 'variable("ThisCard") = ThisCard;' in formatted
    assert compile_source(formatted) == binary
    assert format_module(parse_module(formatted)) == formatted


def test_decompiled_native_variable_named_thiscard_reencodes_identically():
    source = _module(
        'let "ThisCard": int = 7; variable("ThisCard") = ThisCard; '
        'ClassStorage.SetInt("k", variable("ThisCard")); ClassStorage.SetInt("j", TriggeringCard);',
        'global "TriggeringCard": int = 1;',
    )
    binary = compile_source(source)
    decompiled = decompile_module(binary, reject_trailing=True).source
    assert 'let "ThisCard": int' in decompiled
    assert 'variable("ThisCard")' in decompiled
    assert compile_source(decompiled) == binary


def test_errors_are_binding_errors():
    with pytest.raises((SourceBindingError, SourceParseError)):
        parse_module(_module("let ThisCard: int = 0;"))
