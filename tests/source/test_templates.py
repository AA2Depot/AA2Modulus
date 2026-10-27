"""Slotted triggers expand to independently written native modules."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import compile_source, validate_source
from aa2modulus.app.decompile import decompile_module
from aa2modulus.context.limits import SourceLimits
from aa2modulus.syntax.parser.errors import SourceParseError
from aa2modulus.syntax.parser.units import parse_library_source
from tests.support.source import assert_same_binary, parse_module


def library(tmp_path, text):
    (tmp_path / "lib.aa2mi").write_text(text)


def source(items, globals_=""):
    return f'import "lib.aa2mi"; module "M" {{ {globals_} {items} }}'


def expanded(items, globals_=""):
    return f'module "M" {{ {globals_} {items} }}'


def assert_expansion(text, hand, tmp_path, *, roundtrip=False):
    binary = assert_same_binary(text, hand, import_base=tmp_path)
    if roundtrip:
        decompiled = decompile_module(binary).source
        assert compile_source(decompiled) == binary
        assert "import " not in decompiled and "slot " not in decompiled


@pytest.mark.parametrize(
    "typ,value,setter",
    [
        ("int", "7", "Int"),
        ("bool", "true", "Bool"),
        ("float", "float_bits(0x80000000)", "Float"),
        ("string", '"hello"', "String"),
    ],
)
def test_required_slot_types_are_substituted(typ, value, setter, tmp_path):
    library(
        tmp_path,
        f"trigger "
        f'"Init" {{ slot "value" {typ}; on CARD_ADDED; ClassStorage.Set{setter}("k", value); }}',
    )
    text = source(f'import.trigger "Init" {{ slot "value" = {value}; }}')
    hand = expanded(f'trigger "Init" {{ on CARD_ADDED; ClassStorage.Set{setter}("k", {value}); }}')
    assert_expansion(text, hand, tmp_path)


def test_optional_rename_names_the_expanded_trigger(tmp_path):
    library(tmp_path, 'trigger "Init" { slot "value" int; on CARD_ADDED; WriteLog("x"); }')
    text = source('import.trigger "Init" "Renamed" { slot "value" = 7; }')
    assert_expansion(
        text, expanded('trigger "Renamed" { on CARD_ADDED; WriteLog("x"); }'), tmp_path
    )


def test_slot_bindings_are_named_exact_and_order_independent(tmp_path):
    library(
        tmp_path,
        'trigger "T" { slot "key" string; slot "value" int; ClassStorage.SetInt(key, value); }',
    )
    text = source('import.trigger "T" { slot "value" = 9; slot "key" = "k"; }')
    assert_expansion(text, expanded('trigger "T" { ClassStorage.SetInt("k", 9); }'), tmp_path)


def test_templates_preserve_events_defaults_later_locals_macros_and_empty_branches(tmp_path):
    library(
        tmp_path,
        """macro "put" { param "key" string; param "x" int; ClassStorage.SetInt(key, x); }
    trigger "T" { slot "key" string; slot "seed" int;
      on CARD_ADDED; let a: int = later + seed; let later: int = seed;
      a = a + 1; put(key, a); if true {} else if false {} else {} Else;
      raw_action 110("seed", seed) { raw_action 108("child", true); }
    }""",
    )
    text = source('import.trigger "T" { slot "seed" = 3; slot "key" = "k"; }')
    hand = expanded("""trigger "T" { on CARD_ADDED; let a: int = later + 3;
      let later: int = 3; a = a + 1; ClassStorage.SetInt("k", a);
      if true {} else if false {} else {} Else;
      raw_action 110("seed", 3) { raw_action 108("child", true); } }""")
    assert_expansion(text, hand, tmp_path, roundtrip=True)
    actual = parse_module(text, import_base=tmp_path)
    assert actual.triggers[0].events[0].id == 6
    assert actual.triggers[0].gui_actions[-1].raw_reference


def test_site_order_repeated_instantiations_and_unused_templates(tmp_path):
    library(
        tmp_path,
        'trigger "T" { slot "x" string; WriteLog(x); } trigger "Unused" { Notification("unused"); '
        "}",
    )
    text = source(
        'trigger "Before" {} import.trigger "T" "One" { slot "x" = "one"; } trigger "Between" {} '
        'import.trigger "T" "Two" { slot "x" = "two"; } trigger "After" {}'
    )
    hand = expanded(
        'trigger "Before" {} trigger "One" { WriteLog("one"); } trigger "Between" {} trigger "Two" '
        '{ WriteLog("two"); } trigger "After" {}'
    )
    assert_expansion(text, hand, tmp_path)
    actual = parse_module(text, import_base=tmp_path)
    assert [item.name for item in actual.triggers] == ["Before", "One", "Between", "Two", "After"]


@pytest.mark.parametrize("actual", ["Math.RandomInt(1, 9)", "value"])
def test_slot_actuals_use_global_scope_and_repeat_evaluation(actual, tmp_path):
    library(
        tmp_path,
        'trigger "T" { slot "x" int; ClassStorage.SetInt("a", x); ClassStorage.SetInt("b", x); }',
    )
    text = source(f'import.trigger "T" {{ slot "x" = {actual}; }}', "global value: int = 4;")
    hand = expanded(
        f"trigger "
        f'"T" {{ ClassStorage.SetInt("a", {actual}); ClassStorage.SetInt("b", {actual}); }}',
        "global value: int = 4;",
    )
    assert_expansion(text, hand, tmp_path)


def test_slot_actuals_cannot_see_the_locals_of_other_triggers(tmp_path):
    library(
        tmp_path,
        'trigger "T" { slot "x" int; ClassStorage.SetInt("a", x); ClassStorage.SetInt("b", x); }',
    )
    text = source(
        'trigger "Local" { let caller: int = 9; } import.trigger "T" { slot "x" = caller; }'
    )
    assert validate_source(text, import_base=tmp_path).errors[0].code == "UNKNOWN_EXPRESSION_NAME"


def test_unused_actual_is_typed_but_emits_no_expression(tmp_path):
    library(tmp_path, 'trigger "T" { slot "x" int; WriteLog("fixed"); }')
    text = source('import.trigger "T" { slot "x" = Lua.CallInt("effect"); }')
    assert_expansion(text, expanded('trigger "T" { WriteLog("fixed"); }'), tmp_path)
    assert (
        validate_source(source('import.trigger "T" { slot "x" = "wrong"; }'), import_base=tmp_path)
        .errors[0]
        .code
        == "SOURCE_TYPE_MISMATCH"
    )


def test_template_local_hygiene_renames_all_reads_writes_defaults_events_and_raw_refs(tmp_path):
    library(
        tmp_path,
        """macro "use" { param "x" int; ClassStorage.SetInt("k", x); }
    trigger "T" { slot "seed" int; on CARD_ADDED;
      let counter: int = seed; let next: int = counter + 1;
      counter = next; use(counter); for counter from 0 to 2 { break; }
      raw_action 1(raw_expression int 2 { variable "counter"; }, 4);
      raw_action 110("key", raw_expression int 2 { variable "counter"; });
    }""",
    )
    globals_ = 'global counter: string = "global"; global _aa2m_local_0: int = 1;'
    text = source('import.trigger "T" { slot "seed" = _aa2m_local_0; }', globals_)
    hand = expanded(
        """trigger "T" { on CARD_ADDED;
      let _aa2m_local_1: int = _aa2m_local_0; let next: int = _aa2m_local_1 + 1;
      _aa2m_local_1 = next; ClassStorage.SetInt("k", _aa2m_local_1);
      for _aa2m_local_1 from 0 to 2 { break; }
      raw_action 1(raw_expression int 2 { variable "_aa2m_local_1"; }, 4);
      raw_action 110("key", raw_expression int 2 { variable "_aa2m_local_1"; }); }""",
        globals_,
    )
    assert_expansion(text, hand, tmp_path)


def test_definition_builtins_do_not_capture_module_globals(tmp_path):
    library(
        tmp_path,
        'trigger "T" { WriteLog(ThisCard.FullName); ClassStorage.SetInt("day", '
        "Globals.CurrentDay); }",
    )
    text = source('import.trigger "T" {}', 'global "ThisCard": string = "global";')
    hand = expanded(
        'trigger "T" { WriteLog(ThisCard().FullName); ClassStorage.SetInt("day", '
        "Globals.CurrentDay); }",
        'global "ThisCard": string = "global";',
    )
    assert_expansion(text, hand, tmp_path)


@pytest.mark.parametrize(
    ("call", "code", "anchor", "library_note"),
    [
        ('import.trigger "missing" {}', "UNKNOWN_TEMPLATE", 'import.trigger "missing"', False),
        ('import.trigger "T" {}', "MISSING_SLOT", 'import.trigger "T"', True),
        ('import.trigger "T" { slot "extra" = 1; }', "UNKNOWN_SLOT", 'slot "extra"', True),
        (
            'import.trigger "T" { slot "x" = 1; slot "x" = 2; }',
            "DUPLICATE_SLOT_BINDING",
            'slot "x" = 2',
            False,
        ),
        ('import.trigger "T" { slot "x" = "wrong"; }', "SOURCE_TYPE_MISMATCH", '"wrong"', True),
        (
            'import.trigger "T" "" { slot "x" = 1; }',
            "TEMPLATE_TRIGGER_NAME",
            'import.trigger "T"',
            False,
        ),
        (
            'import.trigger "T" { slot "x" = 1; } import.trigger "T" { slot "x" = 2; }',
            "TEMPLATE_TRIGGER_NAME_COLLISION",
            'import.trigger "T" { slot "x" = 2; }',
            False,
        ),
        (
            'import.trigger "T" { slot "x" = 1; } trigger "T" {}',
            "TEMPLATE_TRIGGER_NAME_COLLISION",
            'import.trigger "T" { slot "x" = 1; }',
            False,
        ),
    ],
)
def test_invocation_failures_are_located_at_the_offending_token(
    call, code, anchor, library_note, tmp_path
):
    library(tmp_path, 'trigger "T" { slot "x" int; }')
    text = source(call)
    (error, *_) = validate_source(text, import_base=tmp_path, filename="caller.aa2m").errors
    assert error.code == code
    assert (error.line, error.column) == (1, text.index(anchor) + 1)
    assert error.filename == "caller.aa2m"
    if library_note:
        assert any(note.span.filename.endswith("lib.aa2mi") for note in error.related)


@pytest.mark.parametrize(
    "definition,code",
    [
        ('trigger "" {}', "TEMPLATE_NAME"),
        ('trigger "T" {} trigger "T" {}', "DUPLICATE_TEMPLATE"),
        ('trigger "T" { slot "x" int; slot "x" string; }', "DUPLICATE_TEMPLATE_SLOT"),
        ('trigger "T" { slot "x" invalid; }', "TEMPLATE_SLOT_TYPE"),
        ('trigger "T" { slot "x" type 77; }', "TEMPLATE_SLOT_TYPE"),
        ('trigger "T" { slot "bad-name" int; }', "TEMPLATE_SLOT_NAME"),
        ('trigger "T" { slot "x" int; let x: int = 0; }', "TEMPLATE_SLOT_LOCAL_COLLISION"),
        ('trigger "T" { let x: int = 0; let x: int = 1; }', "DUPLICATE_LOCAL_VARIABLE"),
        ('trigger "T" { slot "x" int; x = 3; }', "TEMPLATE_SLOT_WRITE"),
        ('trigger "T" { slot "x" int; for x from 0 to 1 {} }', "TEMPLATE_SLOT_WRITE"),
        ('trigger "T" { slot "x" int; raw_action 1(x, 1); }', "TEMPLATE_SLOT_WRITE"),
        ('trigger "T" { outside = 1; }', "TEMPLATE_CAPTURE"),
        ('trigger "T" { raw_action 1(0, 1); }', "TEMPLATE_CAPTURE"),
        ('trigger "T" { WriteLog(variable("outside")); }', "TEMPLATE_CAPTURE"),
        (
            'trigger "T" { raw_action 900(raw_expression int 2 { variable "outside"; }); }',
            "TEMPLATE_CAPTURE",
        ),
        (
            'trigger "T" { slot "x" int; raw_action 900(raw_expression int 2 { variable "x"; }); }',
            "TEMPLATE_SLOT_RAW_REFERENCE",
        ),
        ('trigger "T" { Notification(1); }', "SOURCE_TYPE_MISMATCH"),
        (
            'trigger "T" { let x: int = 0; '
            'raw_action 900(raw_expression string 2 { variable "x"; }); }',
            "SOURCE_TYPE_MISMATCH",
        ),
        ('trigger "T" { break; }', "TEMPLATE_LOOP_SCOPE"),
        ('trigger "T" { raw_action 7(true); }', "TEMPLATE_LOOP_SCOPE"),
    ],
)
def test_unused_template_errors_are_checked_at_definition(definition, code, tmp_path):
    library(tmp_path, definition)
    error = validate_source(source(""), import_base=tmp_path).errors[0]
    assert error.code == code
    assert error.filename == str((tmp_path / "lib.aa2mi").resolve())
    assert "library 'lib.aa2mi' imported here" in [note.message for note in error.related]


def test_template_actual_failure_retains_slot_and_invocation_notes(tmp_path):
    library(tmp_path, 'trigger "T" { slot "x" int; }')
    text = source('import.trigger "T" { slot "x" = "bad"; }')
    error = validate_source(text, import_base=tmp_path, filename="call.aa2m").errors[0]
    messages = [note.message for note in error.related]
    assert any("slot 'x'" in message for message in messages)
    assert any("invoked here" in message for message in messages)
    assert any("defined here" in message for message in messages)


def test_unused_template_warnings_are_retained_without_output(tmp_path):
    library(tmp_path, 'trigger "T" { ClassStorage.SetInt("k", Context.NpcCurrentResponse); }')
    result = validate_source(source(""), import_base=tmp_path)
    assert result.is_valid
    assert {note.code for note in result.warnings} == {"REVIEWED_VALUE_CONTEXT_UNKNOWN"}
    assert result.warnings[0].filename.endswith("lib.aa2mi")
    assert not parse_module(source(""), import_base=tmp_path).triggers


def test_template_expansion_budget_boundary_and_repeated_instances(tmp_path):
    library(tmp_path, 'trigger "T" { slot "x" int; ClassStorage.SetInt("a", x); }')
    text = source('import.trigger "T" { slot "x" = 1; }')
    # Trigger, action, and two expressions cost four records per preparation/instance.
    assert validate_source(
        text, import_base=tmp_path, source_limits=SourceLimits(max_expansion_nodes=8)
    ).is_valid
    assert (
        validate_source(
            text, import_base=tmp_path, source_limits=SourceLimits(max_expansion_nodes=7)
        )
        .errors[0]
        .code
        == "TEMPLATE_EXPANSION_LIMIT"
    )
    two = source(
        'import.trigger "T" "One" { slot "x" = 1; } import.trigger "T" "Two" { slot "x" = 2; }'
    )
    assert (
        validate_source(
            two, import_base=tmp_path, source_limits=SourceLimits(max_expansion_nodes=11)
        )
        .errors[0]
        .code
        == "TEMPLATE_EXPANSION_LIMIT"
    )


def test_native_template_local_assignment_and_for_loop_preserve_hygiene(tmp_path):
    library(
        tmp_path,
        'trigger "T" { let count: int = 0; SetVariable(count, 2); ForLoop(count, 0, 2) { '
        "BreakIf(true); } }",
    )
    globals_ = 'global count: string = "outside";'
    text = source('import.trigger "T" {}', globals_)
    hand = expanded(
        'trigger "T" { let _aa2m_local_0: int = 0; _aa2m_local_0 = 2; for _aa2m_local_0 from 0 to '
        "2 { break if true; } }",
        globals_,
    )
    assert_expansion(text, hand, tmp_path)


def test_template_invocation_diagnostics_keep_distinct_origin_chains(tmp_path):
    library(tmp_path, 'trigger "T" { slot "x" int; raw_action 110("key", x); }')
    text = source("""import.trigger "T" "One" { slot "x" = 1; }
    import.trigger "T" "Two" { slot "x" = 2; }""")
    model = parse_module(text, import_base=tmp_path, filename="call.aa2m")
    first, second = model.triggers
    first_notes = first.gui_actions[0].source_span.related
    second_notes = second.gui_actions[0].source_span.related
    assert any(note.span.start_line == 1 and "invoked" in note.message for note in first_notes)
    assert any(note.span.start_line == 2 and "invoked" in note.message for note in second_notes)


@pytest.mark.parametrize(
    ("text", "offender"),
    [
        # `slot` after the event is read as an action name, so its string is unexpected.
        ('trigger "T" { on CARD_ADDED; slot "x" int; }', '"x"'),
        ('trigger "T" { slot "x" int = 0; }', "="),
        ('trigger "T" { import.trigger "Inner" {} }', '"Inner"'),
        ('trigger "T" { macro "inner" {} }', '"inner"'),
    ],
)
def test_library_template_declaration_grammar_restrictions(text, offender):
    with pytest.raises(SourceParseError) as raised:
        parse_library_source(text)
    assert raised.value.code == "SYNTAX_ERROR"
    assert (raised.value.line, raised.value.column) == (1, text.index(offender) + 1)


@pytest.mark.parametrize(
    "actual",
    [
        'raw_expression int 2 { variable "counter"; }',
        'raw_expression int 900 { parameters [ raw_expression int 2 { variable "counter"; } ]; }',
    ],
)
def test_raw_slot_actuals_cannot_capture_template_locals(actual, tmp_path):
    library(
        tmp_path, 'trigger "T" { slot "x" int; let counter: int = 0; ClassStorage.SetInt("k", x); }'
    )
    text = source(f'import.trigger "T" {{ slot "x" = {actual}; }}')
    error = validate_source(text, import_base=tmp_path, filename="actual.aa2m").errors[0]
    assert error.code == "TEMPLATE_CAPTURE"
    assert error.filename == "actual.aa2m"
    assert any("slot 'x'" in note.message for note in error.related)


@pytest.mark.parametrize(
    "actual,code",
    (
        ("raw_expression int 9001 { parameters [ ]; }", "UNKNOWN_EXPRESSION"),
        ('raw_expression int 1 { constant "wrong"; }', "CONSTANT_TYPE_MISMATCH"),
    ),
)
def test_unused_template_slot_checks_raw_actual_semantics(tmp_path, actual, code):
    library(tmp_path, 'trigger "T" { slot "unused" int; WriteLog("constant"); }')
    source_text = source(f'import.trigger "T" {{ slot "unused" = {actual}; }}')

    result = validate_source(source_text, import_base=tmp_path)

    assert {diagnostic.code for diagnostic in result.errors} == {code}
    assert all(len(item.related) >= 3 for item in result.errors)
    assert all(item.path[:3] == ("templates", "T", "slots") for item in result.errors)


def test_raw_slot_actual_globals_keep_scope_provenance_and_types(tmp_path):
    library(
        tmp_path, 'trigger "T" { slot "x" int; let counter: int = 0; ClassStorage.SetInt("k", x); }'
    )
    text = source(
        'import.trigger "T" { slot "x" = raw_expression int 2 { variable "counter"; }; }',
        "global counter: int = 9;",
    )
    hand = expanded(
        'trigger "T" { let _aa2m_local_0: int = 0; ClassStorage.SetInt("k", raw_expression int 2 '
        '{ variable "counter"; }); }',
        "global counter: int = 9;",
    )
    assert_expansion(text, hand, tmp_path)
    wrong = source(
        'import.trigger "T" { slot "x" = raw_expression int 2 { variable "counter"; }; }',
        'global counter: string = "wrong";',
    )
    assert validate_source(wrong, import_base=tmp_path).errors[0].code == "SOURCE_TYPE_MISMATCH"


def test_template_in_nested_library_uses_macro_from_transitive_library(tmp_path):
    (tmp_path / "macros.aa2mi").write_text(
        "macro announce { param message string; WriteLog(message); }", encoding="utf-8"
    )
    (tmp_path / "templates.aa2mi").write_text(
        'import "macros.aa2mi"; trigger "T" { slot "message" string; announce(message); }',
        encoding="utf-8",
    )
    authored = (
        'import "templates.aa2mi"; module "M" { import.trigger "T" { slot "message" = "hello"; } }'
    )
    expanded_source = 'module "M" { trigger "T" { WriteLog("hello"); } }'
    assert_expansion(authored, expanded_source, tmp_path, roundtrip=True)
