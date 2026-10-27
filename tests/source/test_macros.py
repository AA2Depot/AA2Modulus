"""Typed macro composition agrees with independently hand-expanded behavior."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import compile_source, validate_source
from aa2modulus.binary.writer import encode_module
from aa2modulus.context.limits import SourceLimits
from tests.support.source import assert_same_binary, parse_module


def _source(definitions, statements="", declarations=""):
    return f'{definitions}\nmodule "M" {{ trigger "T" {{ {declarations} {statements} }} }}'


@pytest.mark.parametrize(
    "typ,value,setter",
    [
        ("int", "3", "SetInt"),
        ("float", "1.25", "SetFloat"),
        ("bool", "true", "SetBool"),
        ("string", '"value"', "SetString"),
    ],
)
def test_all_formal_types_use_positional_parameters(typ, value, setter):
    definition = f'macro "put" {{ param "value" {typ}; ClassStorage.{setter}("key", value); }}'
    call = f"PuT({value});"
    assert_same_binary(
        _source(definition, call), _source("", f'ClassStorage.{setter}("key", {value});')
    )


def test_arguments_follow_parameter_declaration_order():
    definition = (
        'macro "put" { param "Key" string; param "value" int; ClassStorage.SetInt(Key, value); }'
    )
    assert_same_binary(
        _source(definition, 'put("k", 3);'),
        _source("", 'ClassStorage.SetInt("k", 3);'),
    )


def test_forward_and_after_module_definitions_nested_calls_and_grouping():
    source = """macro "outer" { param "x" int; inner(x + 1); }
    module "M" { trigger "T" { let x: int = 7; outer(x * 2); } }
    macro "inner" { param "x" int; ClassStorage.SetInt("k", x * 3); }"""
    assert_same_binary(
        source, _source("", 'ClassStorage.SetInt("k", ((x * 2) + 1) * 3);', "let x: int = 7;")
    )


def test_actual_variable_with_same_name_as_another_formal_is_not_recursively_substituted():
    definition = (
        'macro "put" { param "x" int; param "y" int; ClassStorage.SetInt("x", x); '
        'ClassStorage.SetInt("y", y); }'
    )
    assert_same_binary(
        _source(definition, "put(y, x);", "let x: int = 1; let y: int = 2;"),
        _source(
            "",
            'ClassStorage.SetInt("x", y); ClassStorage.SetInt("y", x);',
            "let x: int = 1; let y: int = 2;",
        ),
    )


def test_repeated_native_arguments_emit_one_expression_tree_per_use():
    actual = "Math.RandomInt(1, 9)"
    definition = (
        'macro "twice" { param "x" int; ClassStorage.SetInt("a", x); ClassStorage.SetInt("b", x); }'
    )
    assert_same_binary(
        _source(definition, f"twice({actual});"),
        _source("", f'ClassStorage.SetInt("a", {actual}); ClassStorage.SetInt("b", {actual});'),
    )


def test_unused_actual_is_checked_but_not_evaluated_or_emitted():
    definition = 'macro "ignore" { param "x" int; WriteLog("constant"); }'
    assert_same_binary(
        _source(definition, 'ignore(Lua.CallInt("side_effect"));'),
        _source("", 'WriteLog("constant");'),
    )
    result = validate_source(_source(definition, 'ignore("wrong");'))
    assert result.errors[0].code == "SOURCE_TYPE_MISMATCH"
    assert (
        validate_source(_source(definition, "ignore(missing);")).errors[0].code
        == "UNKNOWN_EXPRESSION_NAME"
    )


@pytest.mark.parametrize(
    "actual,code",
    (
        ('raw_expression int 2 { variable "missing"; }', "UNDEFINED_VARIABLE"),
        ("raw_expression int 9001 { parameters [ ]; }", "UNKNOWN_EXPRESSION"),
        ('raw_expression int 1 { constant "wrong"; }', "CONSTANT_TYPE_MISMATCH"),
    ),
)
def test_unused_raw_macro_actuals_still_receive_semantic_validation(actual, code):
    definition = 'macro "ignore" { param "x" int; WriteLog("constant"); }'
    result = validate_source(_source(definition, f"ignore({actual});"))

    assert {diagnostic.code for diagnostic in result.errors} == {code}


def test_definition_builtins_cannot_be_captured_by_globals_or_locals():
    definition = (
        'macro "log_card" { WriteLog(ThisCard.FullName); ClassStorage.SetInt("day", '
        "Globals.CurrentDay); }"
    )
    source = f"""{definition} module "M" {{ global "ThisCard": string = "global";
    trigger "T" {{ let "Globals.CurrentDay": string = "local"; log_card(); }} }}"""
    expanded = """module "M" { global "ThisCard": string = "global";
    trigger "T" { let "Globals.CurrentDay": string = "local";
    WriteLog(ThisCard().FullName); ClassStorage.SetInt("day", Globals.CurrentDay); } }"""
    assert_same_binary(source, expanded)


def test_global_first_actual_lookup_and_later_locals_remain_intact():
    definition = 'macro "put" { param "x" int; ClassStorage.SetInt("k", x); }'
    source = f"""{definition} module "M" {{ global value: int = 3; trigger "T" {{
      put(value); put(later); let value: string = "hidden"; let later: int = 4;
    }} }}"""
    expanded = """module "M" { global value: int = 3; trigger "T" {
      ClassStorage.SetInt("k", value); ClassStorage.SetInt("k", later);
      let value: string = "hidden"; let later: int = 4;
    } }"""
    assert_same_binary(source, expanded)


@pytest.mark.parametrize(
    "body,code",
    [
        ('param "x" int; x = 1;', "MACRO_PARAMETER_WRITE"),
        ('param "x" int; variable("x") = 1;', "MACRO_PARAMETER_WRITE"),
        ('param "x" int; for x from 0 to 3 {}', "MACRO_PARAMETER_WRITE"),
        ("outside = 1;", "MACRO_CAPTURE"),
        ('WriteLog(variable("outside"));', "MACRO_CAPTURE"),
        ("WriteLog(outside);", "UNKNOWN_EXPRESSION_NAME"),
        ("raw_action 1(1, 2);", "MACRO_PARAMETER_WRITE"),
        ("ForLoop(1, 2, 3) {}", "MACRO_PARAMETER_WRITE"),
        ('param "x" int; raw_action 900(raw_expression int 2 { variable "x"; });', "MACRO_CAPTURE"),
        ('raw_action 900(raw_expression int 2 { variable "outside"; });', "MACRO_CAPTURE"),
        ("Notification(1);", "SOURCE_TYPE_MISMATCH"),
        ("MissingAction();", "UNKNOWN_ACTION_NAME"),
        ("break;", "MACRO_LOOP_SCOPE"),
        ("ContinueIf(false);", "MACRO_LOOP_SCOPE"),
        ("raw_action 7(true);", "MACRO_LOOP_SCOPE"),
    ],
)
def test_unused_definitions_reject_types_capture_writes_and_loop_escape(body, code):
    source = _source(f'macro "bad" {{ {body} }}', declarations='let outside: string = "caller";')
    assert validate_source(source).errors[0].code == code


@pytest.mark.parametrize(
    "body",
    [
        "loop { break; continue if false; }",
        "LoopValue() { BreakIf(true); ContinueIf(false); }",
        "raw_action 6() { raw_action 7(true); raw_action 8(false); }",
    ],
)
def test_local_macro_loop_controls_preserve_trees(body):
    assert_same_binary(
        _source(f'macro "work" {{ {body} }}', "loop { work(); }"), _source("", f"loop {{ {body} }}")
    )


def test_nested_macro_cannot_borrow_its_callers_loop_scope():
    source = _source(
        'macro "outer" { loop { inner(); } } macro "inner" { break; }', "loop { outer(); }"
    )
    assert validate_source(source).errors[0].code == "MACRO_LOOP_SCOPE"


@pytest.mark.parametrize(
    "definitions,code",
    [
        ('macro "m" {} macro "M" {}', "DUPLICATE_MACRO"),
        ('macro "Notification" {}', "MACRO_ACTION_COLLISION"),
        ('macro "not-valid" {}', "MACRO_NAME"),
        ('macro "Qualified.Name" {}', "MACRO_NAME"),
        ('macro "macro" {}', "MACRO_NAME"),
        ('macro "m" { param "x" int; param "x" bool; }', "DUPLICATE_MACRO_PARAMETER"),
        ('macro "m" { param "not-valid" int; }', "MACRO_PARAMETER_NAME"),
        ('macro "m" { param "x" invalid; }', "MACRO_PARAMETER_TYPE"),
        ('macro "m" { param "x" type 77; }', "MACRO_PARAMETER_TYPE"),
        ('macro "m" { m(); }', "MACRO_CYCLE"),
        ('macro "a" { b(); } macro "b" { c(); } macro "c" { a(); }', "MACRO_CYCLE"),
    ],
)
def test_invalid_signatures_and_cycles_fail_even_unused(definitions, code):
    assert validate_source(_source(definitions)).errors[0].code == code


@pytest.mark.parametrize(
    "body",
    [
        "let x: int = 0;",
        'trigger "T" {}',
        "on CARD_ADDED;",
        'WriteLog("x"); param "late" int;',
    ],
)
def test_macro_declarations_are_restricted_by_grammar(body):
    assert validate_source(_source(f'macro "bad" {{ {body} }}')).errors[0].code == "SYNTAX_ERROR"


@pytest.mark.parametrize(
    "call,code",
    [
        ("put();", "MACRO_ARITY"),
        ("put(1, 2);", "MACRO_ARITY"),
        ('put("bad");', "SOURCE_TYPE_MISMATCH"),
        ('put { slot "x" = 1; }', "SYNTAX_ERROR"),
        ("put(1) {}", "MACRO_CALL_BLOCK"),
        ('put(1) { WriteLog("extra"); }', "MACRO_CALL_BLOCK"),
        ("unknown { }", "SYNTAX_ERROR"),
        ("WriteLog(put(1));", "UNKNOWN_EXPRESSION_NAME"),
    ],
)
def test_bad_calls_report_stable_diagnostics(call, code):
    source = _source('macro "put" { param "x" int; ClassStorage.SetInt("k", x); }', call)
    assert validate_source(source).errors[0].code == code


def test_zero_argument_macros_and_distinct_case_formals():
    assert_same_binary(
        _source(
            'macro "empty" {} macro "both" { param "x" int; param "X" string; WriteLog(X); }',
            'empty(); both(1, "text");',
        ),
        _source("", 'WriteLog("text");'),
    )


def test_actual_type_error_has_argument_primary_and_definition_invocation_notes():
    source = """macro "put" {
  param "value" int;
  ClassStorage.SetInt("k", value);
}
module "M" { trigger "T" {
  put("wrong");
} }"""
    error = validate_source(source, filename="origins.aa2m").errors[0]
    assert (error.line, error.column) == (6, 7)
    assert {note.span.start_line for note in error.related} == {1, 2, 6}
    assert all(note.span.filename == "origins.aa2m" for note in error.related)
    assert str(error) == (
        "origins.aa2m:6:7: error[SOURCE_TYPE_MISMATCH]: expected int, found string\n"
        "origins.aa2m:2:3: note: formal 'value' declared here\n"
        "origins.aa2m:6:3: note: macro 'put' invoked here\n"
        "origins.aa2m:1:1: note: macro defined here"
    )


def test_nested_expansion_preserves_definition_actual_and_both_invocation_origins():
    source = """macro "inner" { param "x" int; ClassStorage.SetInt("k", x); }
macro "outer" { param "y" int; inner(y + 1); }
module "M" { trigger "T" { outer(2); } }"""
    node = parse_module(source, filename="origins.aa2m").triggers[0].gui_actions[0]
    assert node.source_span.start_line == 1
    assert {note.span.start_line for note in node.source_span.related} == {2, 3}
    expression = node.action.parameters[1].parameters[0]
    assert expression.source_span.start_line == 3
    assert {note.span.start_line for note in expression.source_span.related} >= {1, 2, 3}


def test_raw_payloads_actuals_children_and_empty_branches_remain_exact():
    definition = """macro "raw" { param "x" int;
      raw_action 110("key", x) { raw_action 108("child", true); }
      if true {} else {}
      Else;
    }"""
    actual = (
        'raw_expression int 19 { parameters [ raw_expression int 2 { variable "counter"; } '
        "raw_expression int 1 { constant 1; } ]; }"
    )
    declarations = "let counter: int = 0;"
    source = _source(definition, f"raw({actual});", declarations)
    assert_same_binary(
        source,
        _source(
            "",
            f'raw_action 110("key", {actual}) {{ raw_action 108("child", true); }} '
            "if true {} else {} Else;",
            declarations,
        ),
    )
    action = parse_module(source).triggers[0].gui_actions[0]
    assert action.raw_reference and action.children[0].raw_reference
    assert action.action.parameters[1].raw_reference
    assert action.action.parameters[1].parameters[0].raw_reference


def test_empty_and_unused_definitions_emit_no_records():
    assert_same_binary(
        _source('macro "empty" {} macro "unused" { WriteLog("unused"); }', "empty();"), _source("")
    )


def test_macro_definitions_do_not_leak_between_compilations_in_one_context(context):
    first = _source('macro "log" { WriteLog("first"); }', "log();")
    second = _source('macro "log" { WriteLog("second"); }', "log();")
    first_expected = compile_source(_source("", 'WriteLog("first");'), context=context)
    second_expected = compile_source(_source("", 'WriteLog("second");'), context=context)
    assert first_expected != second_expected
    assert compile_source(first, context=context) == first_expected
    assert compile_source(second, context=context) == second_expected
    # The second definition did not replace the first one for later compilations.
    assert compile_source(first, context=context) == first_expected
    assert (
        validate_source(_source("", "log();"), context=context).errors[0].code
        == "UNKNOWN_ACTION_NAME"
    )


def _doubling(count):
    definitions = 'macro "m0" { WriteLog("leaf"); }\n'
    for index in range(1, count):
        definitions += f'macro "m{index}" {{ m{index - 1}(); m{index - 1}(); }}\n'
    return _source(definitions, f"m{count - 1}();")


def test_substituted_expression_growth_is_preflighted_before_allocation():
    definitions = 'macro "m0" { param "x" int; ClassStorage.SetInt("k", x + x); }\n'
    for index in range(1, 20):
        definitions += f'macro "m{index}" {{ param "x" int; m{index - 1}(x + x); }}\n'
    result = validate_source(
        _source(definitions, "m19(1);"), source_limits=SourceLimits(max_expansion_nodes=1000)
    )
    assert result.errors[0].code == "MACRO_EXPANSION_LIMIT"


def test_aggregate_invocations_and_preparation_have_inclusive_work_budget():
    definition = 'macro "log" { WriteLog("x"); }'  # two HIR records per prepared/call body
    source = _source(definition, "log(); log();")
    assert validate_source(source, source_limits=SourceLimits(max_expansion_nodes=6)).is_valid
    assert (
        validate_source(source, source_limits=SourceLimits(max_expansion_nodes=5)).errors[0].code
        == "MACRO_EXPANSION_LIMIT"
    )
    assert (
        validate_source(_source(definition), source_limits=SourceLimits(max_expansion_nodes=1))
        .errors[0]
        .code
        == "MACRO_EXPANSION_LIMIT"
    )
    assert validate_source(
        _source(""), source_limits=SourceLimits(max_macro_depth=0, max_expansion_nodes=0)
    ).is_valid


def test_macro_depth_is_bounded_even_for_empty_bodies_and_shared_graph_paths():
    definitions = (
        'macro "leaf" {} macro "a" { leaf(); } macro "b" { a(); } macro "c" { b(); leaf(); }'
    )
    assert validate_source(
        _source(definitions), source_limits=SourceLimits(max_macro_depth=4)
    ).is_valid
    assert (
        validate_source(_source(definitions), source_limits=SourceLimits(max_macro_depth=3))
        .errors[0]
        .code
        == "MACRO_DEPTH_LIMIT"
    )
    assert (
        validate_source(_source(definitions), source_limits=SourceLimits(max_macro_depth=0))
        .errors[0]
        .code
        == "MACRO_DEPTH_LIMIT"
    )


def test_output_nesting_accounts_for_definition_and_caller_loops():
    source = _source(
        'macro "deep" { loop { loop { WriteLog("x"); } } }', "loop { loop { deep(); } }"
    )
    assert validate_source(source, source_limits=SourceLimits(max_nesting_depth=6)).is_valid
    assert (
        validate_source(source, source_limits=SourceLimits(max_nesting_depth=5)).errors[0].code
        == "SOURCE_NESTING_LIMIT"
    )


@pytest.mark.parametrize(
    "actual",
    [
        "raw_expression int 1 { constant 7; }",
        'raw_expression int 2 { variable "counter"; }',
        "raw_expression int 3 { named_constant int 1; }",
        "raw_expression int 19 { parameters [ 1 2 ]; }",
    ],
)
def test_all_raw_payload_branches_survive_actual_substitution(actual):
    definition = 'macro "put" { param "x" int; ClassStorage.SetInt("key", x); }'
    declarations = "let counter: int = 0;"
    assert_same_binary(
        _source(definition, f"put({actual});", declarations),
        _source("", f'ClassStorage.SetInt("key", {actual});', declarations),
    )


def test_invalid_raw_macro_actual_fails_authoring_but_expansion_remains_encodable():
    actual = 'raw_expression int 2 { variable "missing"; }'
    definition = 'macro "put" { param "x" int; ClassStorage.SetInt("key", x); }'
    source = _source(definition, f"put({actual});")
    hand = _source("", f'ClassStorage.SetInt("key", {actual});')

    assert {diagnostic.code for diagnostic in validate_source(source).errors} == {
        "UNDEFINED_VARIABLE"
    }
    assert encode_module(parse_module(source)) == encode_module(parse_module(hand))


def test_repeated_raw_actual_errors_keep_emitted_paths_and_all_definition_origins():
    source = """macro "twice" {
  param "x" int;
  ClassStorage.SetInt("a", x);
  ClassStorage.SetInt("b", x);
}
module "M" { trigger "T" {
  twice(raw_expression int 9001 { parameters [ ]; });
} }"""
    errors = validate_source(source, filename="origins.aa2m").errors

    assert len(errors) == 2
    assert all(item.code == "UNKNOWN_EXPRESSION" for item in errors)
    assert all((item.filename, item.line, item.column) == ("origins.aa2m", 7, 9) for item in errors)
    assert errors[0].path != errors[1].path
    assert all(item.path[:3] == ("triggers", 0, "gui_actions") for item in errors)
    for item in errors:
        notes = {(note.message, note.span.start_line) for note in item.related}
        assert ("formal 'x' declared here", 2) in notes
        assert ("macro defined here", 1) in notes
        assert ("macro 'twice' invoked here", 7) in notes


def test_each_emitted_invocation_keeps_its_warning_and_distinct_origin():
    source = """macro "warn" { (3).SetInt("k", Context.NpcCurrentResponse); }
module "M" { trigger "T" {
  warn();
  warn();
} }"""
    warnings = validate_source(source).warnings
    assert len(warnings) == 2
    assert [{note.span.start_line for note in warning.related} for warning in warnings] == [
        {3},
        {4},
    ]


@pytest.mark.parametrize(
    "source,code",
    [
        ('macro "m" {} module "A" {} module "B" {}', "SYNTAX_ERROR"),
        ('module "M" { macro "m" {} }', "SYNTAX_ERROR"),
        ('macro "m" {} import "x.aa2mi"; module "M" {}', "IMPORT_RESOLVER_REQUIRED"),
        (
            'macro "m" { param "x" int; } module "M" { trigger "T" { m(1) { slot "x" = 1; } } }',
            "SYNTAX_ERROR",
        ),
    ],
)
def test_roots_and_mixed_call_forms_remain_restricted(source, code):
    assert validate_source(source).errors[0].code == code


def test_comments_and_keyword_prefixes_work_at_macro_token_boundaries():
    source = """/* macro */ macro "macrovalue" {
      param/* boundary */"slot_value"/* boundary */string;
      WriteLog(slot_value); // slot "fake" = 0;
    }
    module "M" { trigger "T" { macrovalue/* boundary */("// macro"); } }
    // EOF without newline"""
    assert_same_binary(source, _source("", 'WriteLog("// macro");'))


def test_slot_is_a_reserved_name_while_longer_names_with_that_prefix_remain_valid():
    assert validate_source(_source('macro "slot" {}')).errors[0].code == "MACRO_NAME"
    assert (
        validate_source(_source('macro "work" { param "slot" string; }')).errors[0].code
        == "MACRO_PARAMETER_NAME"
    )
    assert_same_binary(
        _source(
            'macro "slot_value" { param "slot_text" string; WriteLog(slot_text); }',
            'slot_value("text");',
        ),
        _source("", 'WriteLog("text");'),
    )
