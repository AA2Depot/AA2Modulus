"""Strict authoring checks and explicit recovery for raw source syntax."""

from __future__ import annotations

from pathlib import Path

import pytest

from aa2modulus.app.compile import (
    CompileError,
    compile_module,
    compile_source,
    validate_source,
)
from aa2modulus.app.decompile import decompile_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.model.values import Value
from tests.support.regression_data import undefined_variables_module
from tests.support.source import assert_same_binary, parse_module

RAW_INVALID_SOURCES = (
    pytest.param(
        'module "Unknown event" { trigger "T" { raw_event 9000; } }',
        {"UNKNOWN_EVENT"},
        id="unknown-event-id",
    ),
    pytest.param(
        """module "Raw expression arity" { trigger "T" {
          raw_action 9000(raw_expression int 19 { parameters [ ]; });
        } }""",
        {"UNKNOWN_ACTION", "EXPRESSION_ARITY"},
        id="known-expression-wrong-arity-under-raw-action",
    ),
    pytest.param(
        """module "Raw unnamed variable" { trigger "T" {
          raw_action 9000(raw_expression int 2 { variable ""; });
        } }""",
        {"UNKNOWN_ACTION", "UNDEFINED_VARIABLE"},
        id="raw-variable-missing-name",
    ),
    pytest.param(
        """module "Raw declaration mismatch" { trigger "T" {
          let x: int = 0;
          raw_action 9000(raw_expression string 2 { variable "x"; });
        } }""",
        {"UNKNOWN_ACTION", "VARIABLE_TYPE_MISMATCH"},
        id="raw-variable-declaration-type-mismatch",
    ),
    pytest.param(
        """module "Raw assignment type" { trigger "T" {
          let x: int = 0;
          raw_action 1(variable("x"), true);
        } }""",
        {"ASSIGNMENT_TYPE_MISMATCH"},
        id="raw-assignment-value-type-mismatch",
    ),
    pytest.param(
        """module "Raw event variable" { trigger "T" {
          raw_event 9000(raw_expression int 2 { variable "missing"; });
        } }""",
        {"UNKNOWN_EVENT", "UNDEFINED_VARIABLE"},
        id="event-raw-expression-variable-resolution",
    ),
    pytest.param(
        """module "Nested raw expressions" { trigger "T" {
          raw_action 9000(raw_expression int 9001 {
            parameters [ raw_expression int 9002 { parameters [ ]; } ];
          });
        } }""",
        {"UNKNOWN_ACTION", "UNKNOWN_EXPRESSION"},
        id="unknown-nested-raw-expression-ids",
    ),
    pytest.param(
        """module "Nested raw gui actions" { trigger "T" {
          raw_action 9000() { raw_action 9001; }
        } }""",
        {"UNKNOWN_ACTION"},
        id="unknown-raw-gui-descendant-action",
    ),
    pytest.param(
        """module "Raw local initializer" { trigger "T" {
          let x: int = raw_expression int 2 { variable "missing"; };
        } }""",
        {"UNDEFINED_VARIABLE"},
        id="local-initializer-raw-expression-variable-resolution",
    ),
    pytest.param(
        """module "Raw named constant" { trigger "T" {
          raw_action 9000(raw_expression int 3 { named_constant int 9001; });
        } }""",
        {"UNKNOWN_NAMED_CONSTANT"},
        id="unknown-named-constant-in-known-scope",
    ),
    pytest.param(
        """module "Raw named constant type" { trigger "T" {
          raw_action 9000(raw_expression int 3 { named_constant string 1; });
        } }""",
        {"UNKNOWN_ACTION", "NAMED_CONSTANT_TYPE_MISMATCH"},
        id="named-constant-type-scope-mismatch",
    ),
)


@pytest.mark.parametrize("source,codes", RAW_INVALID_SOURCES)
def test_raw_records_cannot_bypass_source_semantics(source: str, codes: set[str]) -> None:
    result = validate_source(source)

    assert codes <= {diagnostic.code for diagnostic in result.errors}


@pytest.mark.parametrize(
    "source,code",
    (
        pytest.param(
            """module "Unknown readable expression" { trigger "T" {
              raw_action 9000(UnknownExpression());
            } }""",
            "UNKNOWN_EXPRESSION_NAME",
            id="unknown-expression-call-in-raw-action-argument",
        ),
        pytest.param(
            """module "Unknown readable action" { trigger "T" {
              raw_action 9000() { UnknownAction(); }
            } }""",
            "UNKNOWN_ACTION_NAME",
            id="unknown-action-call-in-raw-gui-children",
        ),
        pytest.param(
            """module "Undefined raw argument" { trigger "T" {
              raw_action 9000(variable("missing"));
            } }""",
            "UNDEFINED_VARIABLE",
            id="undefined-readable-variable-in-raw-argument",
        ),
        pytest.param(
            """module "Undefined raw child" { trigger "T" {
              raw_action 9000() { missing = 1; }
            } }""",
            "UNDEFINED_VARIABLE",
            id="undefined-readable-variable-in-raw-gui-child",
        ),
        pytest.param(
            """module "Wrong typed raw child" { trigger "T" {
              raw_action 9000() { Notification(1); }
            } }""",
            "SOURCE_TYPE_MISMATCH",
            id="wrong-typed-readable-action-in-raw-gui-children",
        ),
    ),
)
def test_raw_roots_do_not_hide_invalid_readable_descendants(source: str, code: str) -> None:
    result = validate_source(source)

    assert {diagnostic.code for diagnostic in result.errors} == {code}


def test_raw_roots_accept_valid_readable_expression_and_gui_descendants() -> None:
    source = """module "Mixed raw and readable" { trigger "T" {
      raw_action 108(raw_expression string 1 { constant "notice"; }, true) {
        Notification("readable child");
      }
    } }"""

    result = validate_source(source)

    assert result.is_valid, result.diagnostics
    action = parse_module(source).triggers[0].gui_actions[0]
    assert action.action.id == 108
    assert action.action.parameters[0].constant == Value.string("notice")
    assert [child.action.id for child in action.children] == [108]
    assert action.children[0].action.parameters[0].constant == Value.string("readable child")


@pytest.mark.parametrize(
    ("raw", "readable"),
    (
        pytest.param(
            'raw_action 108("notice", true);',
            'Notification("notice", true);',
            id="action",
        ),
        pytest.param("raw_event 1;", "on CLOTHES_CHANGED;", id="event"),
        pytest.param(
            "let counter: int = 0; "
            'raw_action 9(raw_expression int 2 { variable "counter"; }, 0, 1);',
            "let counter: int = 0; for counter from 0 to 1 {}",
            id="variable",
        ),
        pytest.param(
            'raw_action 108(raw_expression string 1 { constant "notice"; }, true);',
            'Notification("notice", true);',
            id="constant",
        ),
        pytest.param(
            'let counter: int = 0; raw_action 1(raw_expression int 2 { variable "counter"; }, '
            "raw_expression int 3 { named_constant int 1; });",
            "let counter: int = 0; counter = Constants.Relationship.LOVE;",
            id="named-constant",
        ),
    ),
)
def test_semantically_valid_known_raw_forms_equal_their_readable_spelling(raw, readable):
    def source(body: str) -> str:
        return f'module "M" {{ trigger "T" {{ {body} }} }}'

    assert validate_source(source(raw)).is_valid
    assert_same_binary(source(raw), source(readable))


def test_readable_parent_still_checks_raw_child_return_type() -> None:
    source = """module "Readable parent" { trigger "T" {
      Notification(raw_expression int 1 { constant 1; }, true);
    } }"""

    result = validate_source(source)

    assert {diagnostic.code for diagnostic in result.errors} == {"SOURCE_TYPE_MISMATCH"}


def test_compile_module_rejects_a_model_with_unknown_raw_records() -> None:
    module = parse_module(
        """module "Recover unknown records" { trigger "T" {
          raw_event 9000(raw_expression int 2 { variable "missing"; });
          raw_action 9000(raw_expression int 9001 { parameters [ ]; });
        } }"""
    )

    with pytest.raises(CompileError) as raised:
        compile_module(module)
    assert {diagnostic.code for diagnostic in raised.value.diagnostics} >= {
        "UNKNOWN_EVENT",
        "UNKNOWN_ACTION",
        "UNKNOWN_EXPRESSION",
        "UNDEFINED_VARIABLE",
    }


def test_invalid_raw_definitions_are_checked_even_when_unused(tmp_path: Path) -> None:
    macro_source = """macro "unused" { raw_action 9000; }
      module "M" { trigger "T" {} }"""
    with pytest.raises(CompileError) as macro_error:
        compile_source(macro_source)
    assert "UNKNOWN_ACTION" in {d.code for d in macro_error.value.diagnostics}

    library = tmp_path / "bad-template.aa2mi"
    library.write_text('trigger "Unused" { raw_action 9000; }', encoding="utf-8")
    intermediary = tmp_path / "intermediary.aa2mi"
    intermediary.write_text('import "bad-template.aa2mi"; trigger "Other" {}', encoding="utf-8")
    importing_source = """import "bad-template.aa2mi";
      module "M" { trigger "T" {} }"""
    with pytest.raises(CompileError) as template_error:
        compile_source(importing_source, import_base=tmp_path)
    assert "UNKNOWN_ACTION" in {d.code for d in template_error.value.diagnostics}

    nested_source = importing_source.replace("bad-template.aa2mi", "intermediary.aa2mi")
    with pytest.raises(CompileError) as nested_error:
        compile_source(nested_source, import_base=tmp_path)
    assert "UNKNOWN_ACTION" in {d.code for d in nested_error.value.diagnostics}


def test_raw_undefined_variables_report_locations_and_remain_recoverable() -> None:
    binary = encode_module(undefined_variables_module())
    recovered_source = decompile_module(binary).source

    errors = validate_source(recovered_source).errors

    assert len(errors) == 2
    assert {(d.code, d.line, d.column) for d in errors} == {
        ("UNDEFINED_VARIABLE", 6, 36),
        ("UNDEFINED_VARIABLE", 7, 37),
    }
    assert all("missing" in d.message for d in errors)
    assert encode_module(parse_module(recovered_source)) == binary


def test_declared_unusual_for_loop_target_remains_valid() -> None:
    source = """module "Unusual loop name" { trigger "T" {
      let global_or_local_var_only: int = 0;
      raw_action 9(variable("global_or_local_var_only"), 0, 1);
    } }"""
    readable = """module "Unusual loop name" { trigger "T" {
      let global_or_local_var_only: int = 0;
      for global_or_local_var_only from 0 to 1 {}
    } }"""

    assert validate_source(source).is_valid
    assert_same_binary(source, readable)


@pytest.mark.parametrize("name", ("target", "local_only"))
def test_raw_references_to_missing_or_foreign_locals_suggest_a_module_global(name) -> None:
    source = f"""module "Context" {{
      trigger "Provider" {{ let local_only: int = 0; }}
      trigger "Reader" {{ raw_action 9(raw_expression int 2 {{ variable "{name}"; }}, 0, 1); }}
    }}"""

    errors = validate_source(source).errors

    assert {item.code for item in errors} == {"UNDEFINED_VARIABLE"}
    assert {item.help for item in errors} == {
        f"declare it in this module: `global {name}: int = 0;`"
    }


def test_raw_identifier_overflow_is_an_authoring_error_and_writer_still_checks_model() -> None:
    source = 'module "Overflow" { trigger "T" { raw_action 2147483648; } }'

    result = validate_source(source)
    assert {diagnostic.code for diagnostic in result.errors} == {"UNKNOWN_ACTION"}

    overflow_model = parse_module(source)
    with pytest.raises(ValueError):
        encode_module(overflow_model)
