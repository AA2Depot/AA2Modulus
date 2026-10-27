"""``@allow`` acknowledges known native hazards without changing the binary."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import (
    compile_source,
    compile_source_with_warnings,
    validate_source,
)
from aa2modulus.app.decompile import decompile_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.cli.common import EXIT_OK
from aa2modulus.cli.main import main
from aa2modulus.metadata.schema import MetadataError
from aa2modulus.syntax.parser.errors import SourceParseError
from aa2modulus.syntax.parser.units import parse_source_ast, parse_source_unit
from tests.support.policy import edited_policy, policy_context
from tests.support.source import parse_module

REVIEWED = "REVIEWED_VALUE_TYPE_MISMATCH"
DEFECT = "NATIVE_DEFECTIVE_EXPRESSION"
INT100 = "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH"

LET = """module "M" { trigger "T" { on PC_RESPONSE;
  @allow(REVIEWED_VALUE_TYPE_MISMATCH)
  let value: int = Context.NpcCurrentResponse; } }"""
DEFECT_SOURCE = """module "M" { trigger "T" { on CARD_ADDED;
  @allow(NATIVE_DEFECTIVE_EXPRESSION)
  Notification(Text.Replace(0, 1, 2, "x")); } }"""
INT100_SOURCE = """module "M" { trigger "T" { on PC_RESPONSE;
  @allow(EXPRESSION_METADATA_RETURN_TYPE_MISMATCH, REVIEWED_VALUE_TYPE_MISMATCH)
  let value: int = Context.NpcOriginalResponse; } }"""
MACRO_BODY = 'ClassStorage.SetInt("key", Context.NpcCurrentResponse);'


def _by_code(result, code):
    return [item for item in result.diagnostics if item.code == code]


def _errors(result):
    return {item.code for item in result.diagnostics if item.severity == "error"}


def _without_allows(source: str) -> str:
    return "\n".join(line for line in source.splitlines() if "@allow" not in line)


def _acknowledged(result, code, where):
    (finding,) = _by_code(result, code)
    assert finding.severity == "warning"
    assert any(
        note.startswith(f"acknowledged by @allow({code}) at {where}") for note in finding.notes
    )
    return finding


@pytest.mark.parametrize(
    ("source", "codes", "attribute_columns"),
    [
        (LET, [REVIEWED], [10]),
        (DEFECT_SOURCE, [DEFECT], [10]),
        (INT100_SOURCE, [INT100, REVIEWED], [10, 52]),
    ],
    ids=["reviewed", "defective", "int100"],
)
def test_each_permitted_code_is_acknowledged_and_bytes_are_unchanged(
    source, codes, attribute_columns
):
    result = validate_source(source)
    assert not _errors(result)
    for code, column in zip(codes, attribute_columns, strict=True):
        _acknowledged(result, code, "<source>:2:3")
        (allowed,) = [
            item
            for item in _by_code(result, "NATIVE_HAZARD_ALLOWED")
            if item.message.startswith(f"@allow({code})")
        ]
        assert allowed.severity == "warning"
        assert (allowed.line, allowed.column) == (2, column)
        assert "not recommended" in allowed.message
        assert "remove this @allow" in allowed.help
    bare = _without_allows(source)
    assert compile_source(source) == encode_module(parse_module(bare))


def test_the_same_source_without_allow_is_still_a_strict_error():
    result = validate_source(_without_allows(LET))
    assert _errors(result) == {REVIEWED}


def test_resave_warning_next_to_an_acknowledged_finding_is_untouched():
    result = validate_source(INT100_SOURCE)
    (resave,) = _by_code(result, "NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE")
    assert resave.severity == "warning"
    assert not any("acknowledged" in note for note in resave.notes)


def test_unit_records_each_attribute_with_code_and_target_spans():
    source = 'module "M" {\n@allow(NATIVE_DEFECTIVE_EXPRESSION)\n trigger "T" { on PC_RESPONSE; } }'
    (allow,) = parse_source_unit(source).allows
    assert allow.codes == (DEFECT,)
    assert (allow.source_span.start_line, allow.source_span.start_column) == (2, 1)
    assert (allow.code_spans[0].start_line, allow.code_spans[0].start_column) == (2, 8)
    assert (allow.target_span.start_line, allow.target_span.start_column) == (3, 2)


# --- target kinds -----------------------------------------------------------


TARGET_KINDS = [
    pytest.param(
        """module "M" { trigger "T" { on PC_RESPONSE; loop { if (true) {
      @allow(REVIEWED_VALUE_TYPE_MISMATCH)
      ClassStorage.SetInt("k", Context.NpcCurrentResponse);
      break; } } } }""",
        "<source>:2:7",
        id="statement-nested-in-loop-and-if",
    ),
    pytest.param(
        """module "M" {
  @allow(REVIEWED_VALUE_TYPE_MISMATCH)
  trigger "T" { on PC_RESPONSE; let a: int = Context.NpcCurrentResponse; } }""",
        "<source>:2:3",
        id="trigger",
    ),
    pytest.param(
        """@allow(REVIEWED_VALUE_TYPE_MISMATCH)
module "M" { trigger "T" { on PC_RESPONSE; let v: int = Context.NpcCurrentResponse; } }""",
        "<source>:1:1",
        id="module",
    ),
    pytest.param(
        f"""macro write {{ {MACRO_BODY} }}
module "M" {{ trigger "T" {{ on PC_RESPONSE;
  @allow(REVIEWED_VALUE_TYPE_MISMATCH)
  write(); }} }}""",
        "<source>:3:3",
        id="macro-call-site",
    ),
    pytest.param(
        f"""@allow(REVIEWED_VALUE_TYPE_MISMATCH)
macro write {{ {MACRO_BODY} }}
module "M" {{ trigger "T" {{ on PC_RESPONSE; write(); }} }}""",
        "<source>:1:1",
        id="macro-definition",
    ),
]


@pytest.mark.parametrize(("source", "where"), TARGET_KINDS)
def test_attribute_on_each_target_kind_acknowledges_the_finding_inside_it(source, where):
    result = validate_source(source)
    assert not _errors(result)
    _acknowledged(result, REVIEWED, where)


def test_stacked_attributes_each_cover_their_own_code():
    source = """module "M" { trigger "T" { on PC_RESPONSE;
      @allow(EXPRESSION_METADATA_RETURN_TYPE_MISMATCH)
      @allow(REVIEWED_VALUE_TYPE_MISMATCH)
      let value: int = Context.NpcOriginalResponse; } }"""
    result = validate_source(source)
    assert not _errors(result)
    assert len(_by_code(result, "NATIVE_HAZARD_ALLOWED")) == 2


def test_import_trigger_site_covers_template_findings(tmp_path):
    (tmp_path / "lib.aa2mi").write_text(
        'trigger "Template" { slot "value" int; on PC_RESPONSE; '
        'ClassStorage.SetInt("key", value); }',
        encoding="utf-8",
    )
    allowed = """import "lib.aa2mi";
module "M" {
  @allow(REVIEWED_VALUE_TYPE_MISMATCH)
  import.trigger "Template" { slot "value" = Context.NpcCurrentResponse; } }"""
    result = validate_source(allowed, import_base=tmp_path)
    assert not _errors(result)
    _acknowledged(result, REVIEWED, "<source>:3:3")
    bare = validate_source(_without_allows(allowed), import_base=tmp_path)
    assert _errors(bare) == {REVIEWED}


def test_library_template_may_carry_its_own_allow(tmp_path):
    (tmp_path / "lib.aa2mi").write_text(
        "@allow(REVIEWED_VALUE_TYPE_MISMATCH)\n"
        'trigger "Template" { slot "value" int; on PC_RESPONSE; '
        'ClassStorage.SetInt("key", value); }',
        encoding="utf-8",
    )
    source = """import "lib.aa2mi";
module "M" { import.trigger "Template" { slot "value" = Context.NpcCurrentResponse; } }"""
    result = validate_source(source, import_base=tmp_path)
    assert not _errors(result)
    (finding,) = _by_code(result, REVIEWED)
    assert finding.severity == "warning"


def test_macro_definition_defect_needs_an_allow_inside_the_definition():
    call_site = """macro bad { Notification(Text.Replace(0, 1, 2, "x")); }
module "M" { trigger "T" { on PC_RESPONSE;
  @allow(NATIVE_DEFECTIVE_EXPRESSION)
  bad(); } }"""
    assert DEFECT in _errors(validate_source(call_site))

    definition = """macro bad {
  @allow(NATIVE_DEFECTIVE_EXPRESSION)
  Notification(Text.Replace(0, 1, 2, "x")); }
module "M" { trigger "T" { on PC_RESPONSE; bad(); } }"""
    result = validate_source(definition)
    assert not _errors(result)
    _acknowledged(result, DEFECT, "<source>:2:3")


# --- shadowing and unused attributes -----------------------------------------


def test_innermost_allow_wins_and_the_shadowed_outer_one_is_unused():
    source = """module "M" { trigger "T" { on PC_RESPONSE;
      @allow(REVIEWED_VALUE_TYPE_MISMATCH)
      if (true) {
        @allow(REVIEWED_VALUE_TYPE_MISMATCH)
        ClassStorage.SetInt("k", Context.NpcCurrentResponse); } } }"""
    result = validate_source(source)
    _acknowledged(result, REVIEWED, "<source>:4:9")
    (unused,) = _by_code(result, "UNUSED_ALLOW")
    assert (unused.severity, unused.line) == ("error", 2)


def test_duplicate_code_in_one_attribute_leaves_the_second_unused():
    source = """module "M" { trigger "T" { on PC_RESPONSE;
      @allow(REVIEWED_VALUE_TYPE_MISMATCH, REVIEWED_VALUE_TYPE_MISMATCH)
      let v: int = Context.NpcCurrentResponse; } }"""
    result = validate_source(source)
    (unused,) = _by_code(result, "UNUSED_ALLOW")
    assert unused.column == source.splitlines()[1].rindex(REVIEWED) + 1


def test_allow_without_a_hazard_is_unused():
    source = """module "M" { trigger "T" { on PC_RESPONSE;
      @allow(REVIEWED_VALUE_TYPE_MISMATCH)
      let v: int = 1; } }"""
    result = validate_source(source)
    (unused,) = _by_code(result, "UNUSED_ALLOW")
    assert unused.severity == "error"
    assert (unused.line, unused.column) == (2, 14)
    assert "acknowledges nothing" in unused.message


def test_allow_must_sit_before_the_item_that_reports_the_finding():
    source = """module "M" { trigger "T" { on PC_RESPONSE;
      @allow(REVIEWED_VALUE_TYPE_MISMATCH)
      let ok: int = 1;
      let v: int = Context.NpcCurrentResponse; } }"""
    assert _errors(validate_source(source)) == {REVIEWED, "UNUSED_ALLOW"}


def test_unused_macro_definition_allow_is_not_reported():
    source = """macro idle {
  @allow(REVIEWED_VALUE_TYPE_MISMATCH)
  WriteLog("x"); }
module "M" { trigger "T" { on PC_RESPONSE; WriteLog("y"); } }"""
    result = validate_source(source)
    assert not _by_code(result, "UNUSED_ALLOW")
    assert not _errors(result)


# --- rejected codes -----------------------------------------------------------


@pytest.mark.parametrize("code", ["ASSIGNMENT_TYPE_MISMATCH", "NO_SUCH_CODE"])
def test_codes_outside_the_policy_list_are_not_permitted(code):
    source = f"""module "M" {{ trigger "T" {{ on PC_RESPONSE;
      @allow({code})
      let v: int = 1; }} }}"""
    result = validate_source(source)
    (rejected,) = _by_code(result, "ALLOW_NOT_PERMITTED")
    assert rejected.severity == "error"
    assert (rejected.line, rejected.column) == (2, 14)
    assert f"{code} cannot be acknowledged" in rejected.message
    assert not _by_code(result, "UNUSED_ALLOW")


def test_not_permitted_is_reported_alongside_binding_errors():
    source = """module "M" { trigger "T" { on PC_RESPONSE;
      @allow(NO_SUCH_CODE)
      let v: int = "s"; } }"""
    assert _errors(validate_source(source)) == {"SOURCE_TYPE_MISMATCH", "ALLOW_NOT_PERMITTED"}


# --- syntax -------------------------------------------------------------------


def test_syntax_only_ast_api_rejects_allow_attributes():
    source = 'module "M" {\n@allow(NATIVE_DEFECTIVE_EXPRESSION)\n trigger "T" { on PC_RESPONSE; } }'
    with pytest.raises(SourceParseError) as raised:
        parse_source_ast(source)
    assert raised.value.code == "ALLOW_UNIT_REQUIRED"


# --- policy -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("codes", "message"),
    [
        (["ASSIGNMENT_TYPE_MISMATCH"], "ASSIGNMENT_TYPE_MISMATCH"),
        ([REVIEWED, REVIEWED], "duplicate"),
    ],
    ids=["not-a-hazard", "duplicate"],
)
def test_policy_rejects_non_hazards_and_duplicates(tmp_path, codes, message):
    path = edited_policy(tmp_path, lambda document: document.update(acknowledgeable=codes))
    with pytest.raises(MetadataError, match=message):
        policy_context(path)


def test_an_emptied_policy_list_makes_every_code_not_permitted(tmp_path):
    path = edited_policy(tmp_path, lambda document: document.update(acknowledgeable=[]))
    result = validate_source(LET, context=policy_context(path))
    (rejected,) = _by_code(result, "ALLOW_NOT_PERMITTED")
    assert f"{REVIEWED} cannot be acknowledged" in rejected.message


# --- decompiler ----------------------------------------------------------------


def _roundtrip(source):
    binary = compile_source(source)
    recovered = decompile_module(binary)
    assert compile_source(recovered.source) == binary
    return recovered


@pytest.mark.parametrize(
    ("source", "allow", "target"),
    [
        (LET, f"@allow({REVIEWED})", "let value: int = Context.NpcCurrentResponse;"),
        (DEFECT_SOURCE, f"@allow({DEFECT})", 'Notification(Text.Replace(0, 1, 2, "x"));'),
        (
            INT100_SOURCE,
            f"@allow({INT100}, {REVIEWED})",
            "let value: int = Context.NpcOriginalResponse;",
        ),
    ],
    ids=["reviewed", "defective", "int100"],
)
def test_decompiler_puts_allow_on_its_own_line_and_recompiles_byte_identically(
    source, allow, target
):
    recovered = _roundtrip(source)
    lines = [line.strip() for line in recovered.source.splitlines()]
    assert lines.count(allow) == 1
    assert lines[lines.index(allow) + 1] == target
    assert "NATIVE_HAZARD_ALLOWED" in {item.code for item in recovered.diagnostics}
    assert {item.severity for item in recovered.diagnostics} == {"warning"}


def test_decompiler_puts_one_allow_before_a_whole_if_chain():
    source = (
        """module "M" { trigger "T" { on PC_RESPONSE;
      @allow(REVIEWED_VALUE_TYPE_MISMATCH)
      if (true) { WriteLog("a"); } else if (Context.NpcCurrentResponse == 1) """
        """{ WriteLog("x"); } } }"""
    )
    recovered = _roundtrip(source)
    lines = [line.strip() for line in recovered.source.splitlines()]
    assert lines.count(f"@allow({REVIEWED})") == 1
    assert lines[lines.index(f"@allow({REVIEWED})") + 1].startswith("if (true)")


def test_decompiler_adds_no_allow_without_hazards():
    recovered = _roundtrip('module "M" { trigger "T" { on PC_RESPONSE; WriteLog("a"); } }')
    assert "@allow" not in recovered.source
    assert not recovered.diagnostics


# --- command line --------------------------------------------------------------


def test_cli_validate_and_compile_succeed_with_the_acknowledged_warning(tmp_path, capsys):
    source = tmp_path / "input.aa2m"
    source.write_text(LET, encoding="utf-8")
    output = tmp_path / "OUT"

    assert main(["validate", str(source)]) == EXIT_OK
    validated = capsys.readouterr()
    assert "NATIVE_HAZARD_ALLOWED" in validated.err
    assert "validation passed with 2 warnings" in validated.err

    assert main(["compile", str(source), "--output", str(output)]) == EXIT_OK
    compiled = capsys.readouterr()
    assert "NATIVE_HAZARD_ALLOWED" in compiled.err
    assert "compiled with 2 warnings" in compiled.err
    assert output.read_bytes() == compile_source(LET)


def test_compile_source_with_warnings_returns_bytes_and_acknowledged_findings():
    binary, diagnostics = compile_source_with_warnings(LET)
    assert binary == compile_source(LET)
    assert {item.code for item in diagnostics} >= {REVIEWED, "NATIVE_HAZARD_ALLOWED"}
    assert {item.severity for item in diagnostics} == {"warning"}


def test_attribute_before_import_trigger_parses_and_acknowledges(tmp_path):
    (tmp_path / "lib.aa2mi").write_text(
        'trigger "Template" { slot "value" int; on PC_RESPONSE; WriteLog("x"); }',
        encoding="utf-8",
    )
    source = """import "lib.aa2mi";
module "M" {
  @allow(REVIEWED_VALUE_TYPE_MISMATCH)
  import.trigger "Template" { slot "value" = 1; } }"""
    result = validate_source(source, import_base=tmp_path)
    assert _errors(result) == {"UNUSED_ALLOW"}
