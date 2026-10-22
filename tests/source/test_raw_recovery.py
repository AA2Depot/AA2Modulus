"""Strict authoring checks and explicit recovery for raw source syntax."""

from __future__ import annotations

from pathlib import Path

import pytest

from aa2modulus.app.compile import (
    CompileError,
    compile_module,
    compile_source,
    parse_and_validate_source,
    validate_source,
)
from aa2modulus.app.decompile import decompile_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.validation.validator.module import validate_module
from tests.support.regression_data import undefined_variables_module
from tests.support.source import parse_module

RAW_INVALID_SOURCES = (
    pytest.param(
        'module "Raw action arity" { trigger "T" { raw_action 108; } }',
        {"ACTION_ARITY"},
        id="known-action-wrong-arity",
    ),
    pytest.param(
        'module "Raw action types" { trigger "T" { raw_action 108(1, true); } }',
        {"ACTION_PARAMETER_TYPE"},
        id="known-action-wrong-parameter-types",
    ),
    pytest.param(
        'module "Unknown action" { trigger "T" { raw_action 9000; } }',
        {"UNKNOWN_ACTION"},
        id="unknown-action-id",
    ),
    pytest.param(
        'module "Unknown event" { trigger "T" { raw_event 9000; } }',
        {"UNKNOWN_EVENT"},
        id="unknown-event-id",
    ),
    pytest.param(
        """module "Unknown expression" { trigger "T" {
          raw_action 9000(raw_expression int 9001 { parameters [ ]; });
        } }""",
        {"UNKNOWN_EXPRESSION"},
        id="unknown-expression-id",
    ),
    pytest.param(
        """module "Raw event arity" { trigger "T" {
          raw_event 6(1);
        } }""",
        {"EVENT_ARITY"},
        id="known-event-wrong-arity",
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
        """module "Raw invalid assignment target" { trigger "T" {
          raw_action 1(1, 2);
        } }""",
        {"INVALID_ASSIGNMENT_TARGET"},
        id="raw-assignment-target-must-be-variable",
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
        """module "Raw assignment arity" { trigger "T" {
          let x: int = 0;
          raw_action 1(variable("x"));
        } }""",
        {"ACTION_ARITY"},
        id="raw-assignment-arity",
    ),
    pytest.param(
        """module "Raw For Loop target" { trigger "T" {
          let flag: bool = false;
          raw_action 9(variable("flag"), 0, 1);
        } }""",
        {"FOR_LOOP_TARGET_TYPE"},
        id="raw-for-loop-target-type",
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
    with pytest.raises(CompileError) as raised:
        compile_source(source)
    assert codes <= {diagnostic.code for diagnostic in raised.value.diagnostics}


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
    with pytest.raises(CompileError):
        compile_source(source)


def test_raw_roots_accept_valid_readable_expression_and_gui_descendants() -> None:
    source = """module "Mixed raw and readable" { trigger "T" {
      raw_action 108(raw_expression string 1 { constant "notice"; }, true) {
        Notification("readable child");
      }
    } }"""

    result = validate_source(source)

    assert result.is_valid, result.diagnostics
    assert compile_source(source)


@pytest.mark.parametrize(
    "source",
    (
        'module "Raw valid action" { trigger "T" { raw_action 108("notice", true); } }',
        """module "Raw valid event" { trigger "T" { raw_event 1; } }""",
        """module "Raw valid variable" { trigger "T" {
          let counter: int = 0;
          raw_action 9(raw_expression int 2 { variable "counter"; }, 0, 1);
        } }""",
        """module "Raw valid constant" { trigger "T" {
          raw_action 108(raw_expression string 1 { constant "notice"; }, true);
        } }""",
        """module "Raw valid named constant" { trigger "T" {
          let counter: int = 0;
          raw_action 1(raw_expression int 2 { variable "counter"; },
            raw_expression int 3 { named_constant int 1; });
        } }""",
    ),
)
def test_semantically_valid_known_raw_forms_compile(source: str) -> None:
    assert validate_source(source).is_valid
    assert compile_source(source)


def test_readable_parent_still_checks_raw_child_return_type() -> None:
    source = """module "Readable parent" { trigger "T" {
      Notification(raw_expression int 1 { constant 1; }, true);
    } }"""

    result = validate_source(source)

    assert {diagnostic.code for diagnostic in result.errors} == {"SOURCE_TYPE_MISMATCH"}
    with pytest.raises(CompileError):
        compile_source(source)


def test_model_encode_api_retains_semantically_invalid_raw_source_bytes() -> None:
    source = """module "Recover unknown records" { trigger "T" {
      raw_event 9000(raw_expression int 2 { variable "missing"; });
      raw_action 9000(raw_expression int 9001 { parameters [ ]; });
    } }"""
    module = parse_module(source)

    assert encode_module(module)
    assert {diagnostic.code for diagnostic in validate_module(module).errors} >= {
        "UNKNOWN_EVENT",
        "UNKNOWN_ACTION",
        "UNKNOWN_EXPRESSION",
        "UNDEFINED_VARIABLE",
    }
    with pytest.raises(CompileError):
        compile_module(module)


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

    result = validate_source(recovered_source)
    undefined = [d for d in result.errors if d.code == "UNDEFINED_VARIABLE"]

    assert len(undefined) == 2
    assert {(d.line, d.column) for d in undefined} == {(6, 36), (7, 37)}
    assert all("missing" in d.message for d in undefined)
    assert {d.code for d in result.errors} == {"UNDEFINED_VARIABLE"}
    parsed, validation = parse_and_validate_source(recovered_source)
    assert parsed is not None
    assert validation.errors == result.errors
    assert encode_module(parsed) == binary
    with pytest.raises(CompileError):
        compile_source(recovered_source)
    recovered_module = parse_module(recovered_source)
    assert encode_module(recovered_module) == binary


def test_declared_unusual_for_loop_target_remains_valid() -> None:
    source = """module "Unusual loop name" { trigger "T" {
      let global_or_local_var_only: int = 0;
      raw_action 9(variable("global_or_local_var_only"), 0, 1);
    } }"""

    assert validate_source(source).is_valid
    assert compile_source(source) == encode_module(parse_module(source))


def test_raw_references_to_missing_or_foreign_locals_suggest_a_module_global() -> None:
    source = """module "Context" {
      trigger "Provider" { let local_only: int = 0; }
      trigger "Reader" { raw_action 9(raw_expression int 2 { variable "target"; }, 0, 1); }
    }"""
    missing = [item for item in validate_source(source).errors if item.code == "UNDEFINED_VARIABLE"]
    assert missing
    assert {item.help for item in missing} == {
        "declare it in this module: `global target: int = 0;`"
    }
    foreign_local = source.replace('variable "target"', 'variable "local_only"')
    result = validate_source(foreign_local)
    assert "UNDEFINED_VARIABLE" in {diagnostic.code for diagnostic in result.errors}


def test_raw_identifier_overflow_is_an_authoring_error_and_writer_still_checks_model() -> None:
    source = 'module "Overflow" { trigger "T" { raw_action 2147483648; } }'

    result = validate_source(source)
    assert {diagnostic.code for diagnostic in result.errors} == {"UNKNOWN_ACTION"}
    with pytest.raises(CompileError) as raised:
        compile_source(source)
    assert "UNKNOWN_ACTION" in {diagnostic.code for diagnostic in raised.value.diagnostics}

    overflow_model = parse_module(source)
    with pytest.raises(ValueError):
        encode_module(overflow_model)
