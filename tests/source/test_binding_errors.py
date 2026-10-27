"""Binding reports every independent error once, without cascades."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source
from aa2modulus.context.limits import SourceLimits
from aa2modulus.semantics.binding.state import SourceBindingError
from tests.support.source import parse_module


def _codes(source: str, **options) -> list[tuple[int, str]]:
    result = validate_source(source, filename="errors.aa2m", **options)
    return [(item.line, item.code) for item in result.errors]


def test_independent_errors_in_statements_and_triggers_are_all_reported():
    source = """module "M" {
  trigger "A" { on CARD_ADDED;
    Missing();
    let ok: int = 1;
    ok = alsomissing;
  }
  trigger "B" { on CARD_ADDED;
    Notification(3);
  }
}"""
    assert _codes(source) == [
        (3, "UNKNOWN_ACTION_NAME"),
        (5, "UNKNOWN_EXPRESSION_NAME"),
        (8, "SOURCE_TYPE_MISMATCH"),
    ]


def test_fixing_one_error_leaves_the_others():
    broken = 'module "M" { trigger "T" { on CARD_ADDED;\nMissing();\nOther();\n} }'
    assert _codes(broken) == [(2, "UNKNOWN_ACTION_NAME"), (3, "UNKNOWN_ACTION_NAME")]
    assert _codes(broken.replace("Missing();", "")) == [(3, "UNKNOWN_ACTION_NAME")]


def test_nested_statement_errors_are_independent_of_their_parent():
    source = 'module "M" { trigger "T" { on CARD_ADDED;\nif bad {\nMissing();\n}\n} }'
    assert _codes(source) == [(2, "UNKNOWN_EXPRESSION_NAME"), (3, "UNKNOWN_ACTION_NAME")]


def test_failed_declarations_stay_declared_without_cascades():
    source = """module "M" {
  const C: int = "text";
  global g: int = C;
  global x: int = 0;
  trigger "T" { on CARD_ADDED;
    let y: int = bad;
    x = y;
    x = g;
    x = C;
  }
}"""
    assert _codes(source) == [(2, "SOURCE_TYPE_MISMATCH"), (6, "UNKNOWN_EXPRESSION_NAME")]


def test_constant_chains_through_a_failed_constant_report_it_once():
    source = (
        'module "M" {\nconst A: int = "s";\nconst B: int = A;\ntrigger "T" { on CARD_ADDED; let b: '
        "int = B; } }"
    )
    assert _codes(source) == [(2, "SOURCE_TYPE_MISMATCH")]


def test_a_broken_macro_is_reported_once_not_per_call():
    source = (
        "macro broken { param a int; Missing(a); }\n"
        "macro caller { broken(1); }\n"
        'module "M" { trigger "T" { on CARD_ADDED;\nbroken(1);\nbroken(2);\ncaller();\nOther();\n} '
        "}"
    )
    assert _codes(source) == [(1, "UNKNOWN_ACTION_NAME"), (7, "UNKNOWN_ACTION_NAME")]


def test_a_broken_template_is_reported_once_not_per_instantiation(tmp_path):
    (tmp_path / "lib.aa2mi").write_text(
        'trigger "Broken" { slot n int; on CARD_ADDED; Missing(n); }', encoding="utf-8"
    )
    source = (
        'import "lib.aa2mi"; module "M" {\nimport.trigger "Broken" { slot n = 1; }\n'
        'import.trigger "Broken" "Other" { slot n = 2; }\n'
        'trigger "T" { on CARD_ADDED; Other(); } }'
    )
    result = validate_source(source, filename="errors.aa2m", import_base=tmp_path)
    assert [
        (item.filename.endswith("lib.aa2mi"), item.line, item.code) for item in result.errors
    ] == [
        (True, 1, "UNKNOWN_ACTION_NAME"),
        (False, 4, "UNKNOWN_ACTION_NAME"),
    ]


def test_duplicate_declarations_still_stop_binding_with_earlier_errors_kept(tmp_path):
    (tmp_path / "lib.aa2mi").write_text('trigger "T" { slot x int; }', encoding="utf-8")
    source = (
        'import "lib.aa2mi"; module "M" {\ntrigger "A" { on CARD_ADDED; Missing(); }\n'
        'import.trigger "T" "A" { slot x = 1; }\n'
        'trigger "U" { on CARD_ADDED; Missing(); } }'
    )
    result = validate_source(source, filename="errors.aa2m", import_base=tmp_path)
    assert [(item.line, item.code) for item in result.errors] == [
        (2, "UNKNOWN_ACTION_NAME"),
        (3, "TEMPLATE_TRIGGER_NAME_COLLISION"),
    ]
    duplicate = (
        'module "M" {\nconst A: int = 1;\nconst A: int = 2;\n'
        'trigger "T" { on CARD_ADDED; Missing(); } }'
    )
    assert _codes(duplicate) == [(3, "DUPLICATE_CONST")]


def test_error_cap_stops_with_one_summary_diagnostic():
    statements = "\n".join("Missing();" for _ in range(5))
    source = f'module "M" {{ trigger "T" {{ on CARD_ADDED;\n{statements}\n}} }}'
    codes = _codes(source, source_limits=SourceLimits(max_binding_errors=3))
    assert codes == [
        (2, "UNKNOWN_ACTION_NAME"),
        (3, "UNKNOWN_ACTION_NAME"),
        (4, "UNKNOWN_ACTION_NAME"),
        (5, "SOURCE_BINDING_ERROR_LIMIT"),
    ]


def test_binding_error_carries_every_diagnostic_and_the_first_one():
    source = 'module "M" { trigger "T" { on CARD_ADDED;\nOther();\nMissing();\n} }'
    with pytest.raises(SourceBindingError) as raised:
        parse_module(source)
    assert raised.value.diagnostic == raised.value.diagnostics[0]
    assert [item.line for item in raised.value.diagnostics] == [2, 3]


def test_validator_findings_wait_for_clean_binding():
    # Text.Replace is a validator error; it is reported only once binding succeeds.
    replace = 'Notification(Text.Replace(0, 1, 2, "x"));'
    source = f'module "M" {{ trigger "T" {{ on CARD_ADDED; {replace} Missing(); }} }}'
    assert [code for _, code in _codes(source)] == ["UNKNOWN_ACTION_NAME"]
    clean = source.replace(" Missing();", "")
    assert [code for _, code in _codes(clean)] == ["NATIVE_DEFECTIVE_EXPRESSION"]
