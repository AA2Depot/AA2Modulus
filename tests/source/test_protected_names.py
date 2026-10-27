"""ThisCard and TriggeringCard always mean the built-in; native variables use quoted names."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import compile_source, validate_source
from aa2modulus.app.decompile import decompile_module
from aa2modulus.decompile.format.module import format_module
from tests.support.source import module_source, parse_module


def _code(source: str) -> str:
    result = validate_source(source)
    assert result.errors, source
    return result.errors[0].code


@pytest.mark.parametrize("name", ["ThisCard", "triggeringcard"])
def test_bare_global_and_local_declarations_are_rejected(name):
    assert _code(module_source("", f"global {name}: int = 0;")) == "PROTECTED_NAME"
    assert _code(module_source(f"let {name}: int = 0;")) == "PROTECTED_NAME"


def test_diagnostic_message_explains_the_quoted_form():
    diagnostic = validate_source(module_source("let ThisCard: int = 0;")).errors[0]
    assert diagnostic.message == "'ThisCard' is a protected built-in name"
    assert diagnostic.help == (
        'quote the declaration ("ThisCard") and reference it with variable("ThisCard") '
        "to name a native variable"
    )


SPELLINGS = pytest.mark.parametrize("quoted", [False, True], ids=["bare", "quoted"])


@SPELLINGS
def test_constants_are_rejected_even_when_quoted(quoted):
    spelling = '"ThisCard"' if quoted else "ThisCard"
    assert _code(module_source("", f"const {spelling}: int = 1;")) == "PROTECTED_NAME"


@SPELLINGS
def test_macro_formals_are_rejected_even_when_quoted(quoted):
    spelling = '"triggeringcard"' if quoted else "triggeringcard"
    source = f'macro "m" {{ param {spelling} int; WriteLog("x"); }} ' + module_source("m(1);")
    assert _code(source) == "PROTECTED_NAME"


@SPELLINGS
def test_template_slots_are_rejected_even_when_quoted(quoted, tmp_path):
    spelling = '"ThisCard"' if quoted else "ThisCard"
    (tmp_path / "lib.aa2mi").write_text(
        f'trigger "T" {{ slot {spelling} int; on CARD_ADDED; WriteLog("x"); }}'
    )
    result = validate_source(
        'import "lib.aa2mi"; module "M" { }', import_base=tmp_path, filename="m.aa2m"
    )
    assert result.errors[0].code == "PROTECTED_NAME"


def test_bare_loop_variable_and_assignment_target_are_rejected():
    assert _code(module_source('let "ThisCard": int = 0; for ThisCard from 0 to 3 {}')) == (
        "PROTECTED_NAME"
    )
    assert _code(module_source('let "ThisCard": int = 0; ThisCard = 1;')) == "PROTECTED_NAME"


def test_quoted_variable_declaration_compiles_and_is_reached_through_variable():
    source = module_source(
        'let "ThisCard": int = 7; variable("ThisCard") = 8; '
        'for "ThisCard" from 0 to 2 {} ClassStorage.SetInt("k", variable("ThisCard"));',
        'global "TriggeringCard": int = 1;',
    )
    assert validate_source(source).errors == ()
    module = parse_module(source)
    trigger = module.triggers[0]
    assert module.globals[0].name == "TriggeringCard"
    assert [variable.name for variable in trigger.variables] == ["ThisCard"]
    assignment = trigger.gui_actions[0].action
    assert (assignment.id, assignment.parameters[0].variable_name) == (1, "ThisCard")


def test_builtin_references_ignore_quoted_variables_with_the_same_name():
    declared = 'let "ThisCard": int = 7; let "TriggeringCard": int = 8; '
    uses = (
        'ClassStorage.SetInt("k", ThisCard); ClassStorage.SetInt("j", thiscard); '
        "WriteLog(ThisCard().FullName); ThisCard.SetVirtue(3); WriteLog(thiscard.FullName); "
        "TriggeringCard.AddLike(ThisCard, 5);"
    )
    shadowed = parse_module(module_source(declared + uses))
    plain = parse_module(module_source(uses))
    assert (
        shadowed.to_ir()["triggers"][0]["gui_actions"]
        == plain.to_ir()["triggers"][0]["gui_actions"]
    )


def test_protected_variables_stay_quoted_through_formatting_and_decompilation():
    source = module_source(
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

    decompiled = decompile_module(binary, reject_trailing=True).source
    assert 'let "ThisCard": int' in decompiled
    assert 'variable("ThisCard")' in decompiled
    assert compile_source(decompiled) == binary
