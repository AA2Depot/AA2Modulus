"""Reviewed callback claims follow source trigger context and expansion origins."""

from __future__ import annotations

from aa2modulus.app.compile import compile_source, validate_source
from aa2modulus.binary.reader import decode_module
from aa2modulus.validation.validator.module import validate_module
from tests.support.source import parse_module


def _codes(result):
    return {item.code for item in result.diagnostics}


def test_callback_type_claim_uses_each_trigger_event_and_native_profile():
    source = """module "M" {
      trigger "Safe" { on NPC_RESPONSE; let value: int = Context.NpcCurrentResponse; }
      trigger "Unsafe" { on PC_RESPONSE; let value: int = Context.NpcCurrentResponse; }
    }"""
    strict = validate_source(source)
    native = validate_module(parse_module(source), profile="native")
    for result, severity in ((strict, "error"), (native, "warning")):
        (mismatch,) = [
            item for item in result.diagnostics if item.code == "REVIEWED_VALUE_TYPE_MISMATCH"
        ]
        assert mismatch.severity == severity
        assert mismatch.line == 3
        assert "during PC_RESPONSE" in mismatch.message
        assert "REVIEWED_VALUE_CONTEXT_UNKNOWN" not in _codes(result)


def test_int70_runtime_type_claim_uses_the_reviewed_event_id():
    # Native-format evidence N7 pins INT/70's mixed bool callback to the event.
    matching = validate_source(
        """module "M" { trigger "T" { raw_event 13;
          let value: int = Conversation.IsAnswering; } }"""
    )
    mismatching = validate_source(
        """module "M" { trigger "T" { raw_event 14;
          let value: int = Conversation.IsAnswering; } }"""
    )
    assert "REVIEWED_VALUE_TYPE_MISMATCH" not in _codes(matching)
    (mismatch,) = [
        item for item in mismatching.diagnostics if item.code == "REVIEWED_VALUE_TYPE_MISMATCH"
    ]
    assert mismatch.severity == "error"
    assert "during PC_RESPONSE" in mismatch.message


def test_int99_placeholder_does_not_invent_callback_context():
    # N7 identifies INT/99 as a placeholder returning -1, not an event callback.
    source = """module "M" { trigger "T" { raw_event 14;
          let value: int = raw_expression int 99 { parameters [ ]; }; } }"""
    module = decode_module(compile_source(source), reject_trailing=True).module
    expression = module.triggers[0].variables[0].default_expression
    assert (expression.return_type, expression.id) == (1, 99)
    result = validate_module(module)
    assert "REVIEWED_VALUE_TYPE_MISMATCH" not in _codes(result)
    assert "REVIEWED_VALUE_CONTEXT_UNKNOWN" not in _codes(result)


def test_int100_declared_scope_and_resave_hazards_remain_separate():
    # Native-format evidence N6 separates the INT lookup from BOOL declaration/save.
    source = """module "M" { trigger "T" { on PC_RESPONSE;
      let value: int = Context.NpcOriginalResponse;
    } }"""
    strict = validate_source(source)
    native = validate_module(parse_module(source), profile="native")
    strict_by_code = {item.code: item for item in strict.diagnostics}
    native_by_code = {item.code: item for item in native.diagnostics}
    assert strict_by_code["EXPRESSION_METADATA_RETURN_TYPE_MISMATCH"].severity == "error"
    assert strict_by_code["REVIEWED_VALUE_TYPE_MISMATCH"].severity == "error"
    assert strict_by_code["NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE"].severity == "warning"
    assert native_by_code["EXPRESSION_METADATA_RETURN_TYPE_MISMATCH"].severity == "warning"
    assert native_by_code["REVIEWED_VALUE_TYPE_MISMATCH"].severity == "warning"
    resave = native_by_code["NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE"]
    assert resave.severity == "warning"
    assert "is an int here" in resave.message
    assert "saves it as a bool" in resave.message


def test_int101_checks_every_known_event_in_a_multi_event_trigger():
    source = """module "M" { trigger "T" { raw_event 8; raw_event 14;
      let value: int = Context.NpcCurrentResponse;
    } }"""
    result = validate_source(source)
    (mismatch,) = [
        item for item in result.diagnostics if item.code == "REVIEWED_VALUE_TYPE_MISMATCH"
    ]
    assert mismatch.severity == "error"
    assert "during PC_RESPONSE AAUnlimited returns" in mismatch.message
    assert "during NPC_RESPONSE AAUnlimited" not in mismatch.message


def test_macro_event_check_uses_each_invocations_context_and_origin():
    source = """macro write { ClassStorage.SetInt("key", Context.NpcCurrentResponse); }
module "M" {
  trigger "Safe" { on NPC_RESPONSE; write(); }
  trigger "Unsafe" { on PC_RESPONSE; write(); }
}"""
    result = validate_source(source)
    mismatches = [
        item for item in result.diagnostics if item.code == "REVIEWED_VALUE_TYPE_MISMATCH"
    ]
    assert len(mismatches) == 1
    assert mismatches[0].severity == "error"
    assert mismatches[0].source_span is not None
    assert mismatches[0].related
    assert mismatches[0].related[0].message == "macro 'write' invoked here"
    assert mismatches[0].related[0].span.start_line == 4
    assert "REVIEWED_VALUE_CONTEXT_UNKNOWN" not in _codes(result)


def test_unused_macro_does_not_claim_unknown_invocation_context():
    source = """macro "unused" { ClassStorage.SetInt("key", Context.NpcCurrentResponse); }
module "M" { trigger "T" {} }"""
    result = validate_source(source)
    assert result.is_valid
    assert "REVIEWED_VALUE_CONTEXT_UNKNOWN" not in _codes(result)


def test_imported_trigger_keeps_event_context_and_source_origin(tmp_path):
    (tmp_path / "lib.aa2mi").write_text(
        'trigger "Imported" { on PC_RESPONSE; let value: int = Context.NpcCurrentResponse; }',
        encoding="utf-8",
    )
    source = 'import "lib.aa2mi"; module "M" { import.trigger "Imported" {} }'
    result = validate_source(source, import_base=tmp_path)
    (mismatch,) = [
        item for item in result.diagnostics if item.code == "REVIEWED_VALUE_TYPE_MISMATCH"
    ]
    assert mismatch.severity == "error"
    assert mismatch.related
    assert any("lib.aa2mi" in item.message for item in mismatch.related)


def test_template_slot_is_checked_after_event_context_expansion(tmp_path):
    (tmp_path / "lib.aa2mi").write_text(
        'trigger "Template" { slot "value" int; on PC_RESPONSE; '
        'ClassStorage.SetInt("key", value); }',
        encoding="utf-8",
    )
    source = """import "lib.aa2mi";
module "M" { import.trigger "Template" { slot "value" = Context.NpcCurrentResponse; } }"""
    result = validate_source(source, import_base=tmp_path)
    (mismatch,) = [
        item for item in result.diagnostics if item.code == "REVIEWED_VALUE_TYPE_MISMATCH"
    ]
    assert mismatch.severity == "error"
    assert mismatch.related
