"""Compile-time source constants substitute literals and never reach SIR or the binary."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import compile_source
from aa2modulus.app.decompile import decompile_module
from aa2modulus.context.limits import SourceLimitError, SourceLimits
from aa2modulus.semantics.binding.state import SourceBindingError
from aa2modulus.syntax.imports import SourceImportError
from aa2modulus.syntax.parser.errors import SourceParseError
from tests.support.source import parse_module


def _module(body: str, items: str = "") -> str:
    return f'module "M" {{ {items} trigger "T" {{ on CARD_ADDED; {body} }} }}'


def _error(source: str, **kwargs):
    with pytest.raises((SourceBindingError, SourceImportError, SourceParseError)) as caught:
        parse_module(source, **kwargs)
    error = caught.value
    diagnostic = getattr(error, "diagnostic", error)
    code = diagnostic.code
    line = diagnostic.line
    column = diagnostic.column
    return code, line, column


def _same(constants: str, literal: str, **kwargs) -> None:
    assert parse_module(constants, **kwargs).to_ir() == parse_module(literal).to_ir()
    assert compile_source(constants, **kwargs) == compile_source(literal)


OWNER_EXAMPLE = """module "Test Module" {
  description "Testing different language capabilities";
  const "ModuleName": string = "Test Module";
  const "With Spaces": string = "Test Module With Spaces";

  trigger "Init" {
    on CARD_ADDED;
    if (ThisCard == TriggeringCard) {
      ThisCard.SetBool(ModuleName, true);
      Notification(const("With Spaces") + " testing");
    }
  }
}"""

OWNER_LITERALS = """module "Test Module" {
  description "Testing different language capabilities";

  trigger "Init" {
    on CARD_ADDED;
    if (ThisCard == TriggeringCard) {
      ThisCard.SetBool("Test Module", true);
      Notification("Test Module With Spaces" + " testing");
    }
  }
}"""


def test_owner_example_equals_the_literal_module_byte_for_byte():
    _same(OWNER_EXAMPLE, OWNER_LITERALS)
    decompiled = decompile_module(compile_source(OWNER_EXAMPLE)).source
    assert "const" not in decompiled
    assert "Test Module With Spaces" in decompiled


def test_references_chain_in_any_order_and_unused_constants_emit_nothing():
    constants = _module(
        "Notification(B);",
        'const B: string = const("A"); const A: string = "hi"; const Unused: int = 3;',
    )
    _same(constants, _module('Notification("hi");'))


@pytest.mark.parametrize(
    ("type_name", "literal"),
    [("int", "-5"), ("bool", "true"), ("float", "1.5"), ("string", '"s"')],
)
def test_every_constant_type_substitutes_its_literal(type_name, literal):
    use = {
        "int": "ThisCard.SetInt(Slot0, K);",
        "bool": "ThisCard.SetBool(Slot0, K);",
        "float": "ThisCard.SetFloat(Slot0, K);",
        "string": "ThisCard.SetString(Slot0, K);",
    }[type_name]
    items = f'const K: {type_name} = {literal}; const Slot0: string = "slot";'
    plain = use.replace("K", literal).replace("Slot0", '"slot"')
    _same(_module(use, items), _module(plain))


def test_float_bits_constant_keeps_exact_bits():
    items = "const F: float = float_bits(0x7fc00001);"
    use = 'ThisCard.SetFloat("f", F);'
    _same(_module(use, items), _module('ThisCard.SetFloat("f", float_bits(0x7fc00001));'))


def test_global_initializer_accepts_constants_but_state_form_stays_literal():
    items = 'const Start: int = 7; global a: int = Start; global b: int = const("Start");'
    _same(
        _module("", items),
        _module("", "global a: int = 7; global b: int = 7;"),
    )
    with pytest.raises(SourceParseError):
        parse_module(
            _module(
                "",
                "const Start: int = 7; global a: int "
                "{ default Start; current 1; initialized true; }",
            )
        )


def test_constants_work_as_receivers():
    items = "const LEAD: int = 0;"
    _same(
        _module("LEAD.SetVirtue(3); let v: int = LEAD.Virtue;", items),
        _module("0.SetVirtue(3); let v: int = 0.Virtue;".replace("0.", "(0).")),
    )
    _same(
        _module('const("LEAD").SetVirtue(3);', items),
        _module("(0).SetVirtue(3);"),
    )


def test_quoted_keyword_like_names_and_prefix_identifiers_are_ordinary():
    items = (
        'const "int": string = "a"; const "if": string = "b"; const const_x: string = "c"; '
        'const constant: string = "d"; const constant_x: string = "e";'
    )
    use = (
        'Notification(const("int")); Notification(const("if")); Notification(const_x); '
        'Notification(const("constant")); Notification(constant_x);'
    )
    plain = (
        'Notification("a"); Notification("b"); Notification("c"); Notification("d"); '
        'Notification("e");'
    )
    _same(_module(use, items), _module(plain))


def test_raw_constant_payload_and_const_prefixed_identifiers_still_parse():
    source = _module(
        "let constant_x: int = raw_expression int 1 { constant 4; }; let const_y: int = constant_x;"
    )
    assert parse_module(source) is not None


def test_const_is_not_an_identifier():
    for body in ("let const: int = 1;", "const = 1;", "on const;"):
        with pytest.raises(SourceParseError):
            parse_module(_module(body))
    assert _error(_module("", "global const: int = 1;"))[0] == "SYNTAX_ERROR"


def test_global_and_trigger_names_may_still_be_quoted_const():
    parse_module(_module('let "const": int = 1;'))


def test_variable_forms_never_resolve_constants():
    items = "const K: int = 1;"
    assert _error(_module('let x: int = variable("K");', items))[0] == "UNDEFINED_VARIABLE"
    assert _error(_module('variable("K") = 2;', items))[0] == "UNDEFINED_VARIABLE"
    raw = 'let x: int = raw_expression int 2 { variable "K"; };'
    # A raw variable payload names a variable only; no constant is substituted.
    expression = parse_module(_module(raw, items)).triggers[0].variables[0].default_expression
    assert expression.raw_reference
    assert (expression.id, expression.variable_name) == (2, "K")


def test_type_mismatch_and_range_errors_are_located():
    source = 'module "M" {\n  const A: int = "text";\n}'
    assert _error(source) == ("SOURCE_TYPE_MISMATCH", 2, 18)
    source = 'module "M" {\n  const A: float = 1.0e60;\n}'
    assert _error(source) == ("FLOAT_OUT_OF_RANGE", 2, 20)
    source = 'module "M" {\n  const A: int = 2147483648;\n  global g: int = A;\n}'
    assert _error(source) == ("INT_OUT_OF_RANGE", 2, 18)
    source = 'module "M" {\n  const A: bool = true;\n  const B: int = A;\n}'
    assert _error(source) == ("SOURCE_TYPE_MISMATCH", 3, 18)
    source = _module('ThisCard.SetInt("k", K);', 'const K: string = "s";')
    assert _error(source)[0] == "SOURCE_TYPE_MISMATCH"


def test_cycles_are_rejected_even_when_unused():
    source = 'module "M" {\n  const A: int = B;\n  const B: int = const("A");\n}'
    assert _error(source) == ("CONST_CYCLE", 3, 18)
    assert _error('module "M" { const A: int = A; }')[0] == "CONST_CYCLE"


def test_duplicate_and_undefined_constants():
    source = 'module "M" {\n  const A: int = 1;\n  const A: int = 2;\n}'
    assert _error(source) == ("DUPLICATE_CONST", 3, 3)
    source = 'const A: int = 1;\nmodule "M" {\n  const A: int = 2;\n}'
    assert _error(source) == ("DUPLICATE_CONST", 3, 3)
    source = 'module "M" {\n  const A: int = Missing;\n}'
    assert _error(source) == ("UNDEFINED_CONST", 2, 18)
    source = _module('Notification(const("Missing"));')
    assert _error(source)[0] == "UNDEFINED_CONST"
    source = 'module "M" {\n  global g: int = const("Nope");\n}'
    assert _error(source) == ("UNDEFINED_CONST", 2, 19)


def test_constant_name_collisions_are_errors_on_the_other_declaration(tmp_path):
    items = "const K: int = 1;"
    source = f'module "M" {{\n  {items}\n  global K: int = 2;\n}}'
    assert _error(source) == ("CONST_NAME_COLLISION", 3, 3)
    source = (
        f"module "
        f'"M" {{\n  {items}\n  trigger "T" {{\n    on CARD_ADDED;\n    let K: int = 2;\n  }}\n}}'
    )
    assert _error(source) == ("CONST_NAME_COLLISION", 5, 5)
    libraries = {
        "macro": "const K: int = 1; macro m {\n param K int;\n}",
        "slot": 'const K: int = 1; trigger "t" {\n slot K int;\n on CARD_ADDED;\n}',
        "local": 'const K: int = 1; trigger "t" {\n on CARD_ADDED;\n let K: int = 0;\n}',
    }
    expected = {
        "macro": ("CONST_NAME_COLLISION", 2, 2),
        "slot": ("CONST_NAME_COLLISION", 2, 2),
        "local": ("CONST_NAME_COLLISION", 3, 2),
    }
    for name, text in libraries.items():
        (tmp_path / f"{name}.aa2mi").write_text(text, encoding="utf-8")
        imported = f'import "{name}.aa2mi"; module "M" {{ }}'
        assert _error(imported, import_base=tmp_path) == expected[name]


def test_assignment_and_for_targets_naming_a_constant_are_rejected():
    items = "const K: int = 1;"
    source = f'module "M" {{ {items}\n trigger "T" {{ on CARD_ADDED;\n   K = 2;\n }} }}'
    assert _error(source) == ("CONST_ASSIGNMENT", 3, 4)
    source = (
        f'module "M" {{ {items}\n trigger "T" {{ on CARD_ADDED;\n   for K from 0 to 3 {{ }}\n }} }}'
    )
    assert _error(source) == ("CONST_ASSIGNMENT", 3, 8)


def test_library_constants_work_in_module_macros_and_templates_with_diamonds(tmp_path):
    (tmp_path / "base.aa2mi").write_text(
        'const Greeting: string = "hello"; const Limit: int = 3;', encoding="utf-8"
    )
    (tmp_path / "a.aa2mi").write_text(
        'import "base.aa2mi"; macro say { Notification(Greeting); } '
        'trigger "Tpl" { slot Extra int; on CARD_ADDED; '
        'ThisCard.SetInt(const("Greeting"), Limit + Extra); }',
        encoding="utf-8",
    )
    (tmp_path / "b.aa2mi").write_text(
        'import "base.aa2mi"; const Other: int = Limit;', encoding="utf-8"
    )
    constants = (
        'import "a.aa2mi"; import "b.aa2mi"; module "M" {\n'
        '  import.trigger "Tpl" { slot Extra = Other; }\n'
        '  trigger "T" { on CARD_ADDED; say(); Notification(Greeting); }\n}'
    )
    literals = (
        'module "M" {\n'
        '  trigger "Tpl" { on CARD_ADDED; ThisCard.SetInt("hello", 3 + 3); }\n'
        '  trigger "T" { on CARD_ADDED; Notification("hello"); Notification("hello"); }\n}'
    )
    assert parse_module(constants, import_base=tmp_path).to_ir() == parse_module(literals).to_ir()
    assert compile_source(constants, import_base=tmp_path) == compile_source(literals)


def test_distinct_library_definitions_with_one_name_fail_even_unused(tmp_path):
    (tmp_path / "a.aa2mi").write_text("const K: int = 1;", encoding="utf-8")
    (tmp_path / "b.aa2mi").write_text("const K: int = 2;", encoding="utf-8")
    source = 'import "a.aa2mi"; import "b.aa2mi"; module "M" { }'
    assert _error(source, import_base=tmp_path)[0] == "DUPLICATE_CONST"


def test_module_constants_are_not_visible_in_macros_or_templates_but_slots_see_them(tmp_path):
    (tmp_path / "m.aa2mi").write_text("macro m { Notification(Local); }", encoding="utf-8")
    (tmp_path / "t.aa2mi").write_text(
        'trigger "tpl" { on CARD_ADDED; Notification(const("Local")); }', encoding="utf-8"
    )
    code, *_ = _error(
        'import "m.aa2mi"; module "M" { const Local: string = "x"; '
        'trigger "T" { on CARD_ADDED; m(); } }',
        import_base=tmp_path,
    )
    assert code in {"UNKNOWN_EXPRESSION_NAME", "MACRO_CAPTURE"}
    code, *_ = _error(
        'import "t.aa2mi"; module "M" { const Local: string = "x"; import.trigger "tpl" { } }',
        import_base=tmp_path,
    )
    assert code == "UNDEFINED_CONST"


def test_hidden_module_constants_get_a_declare_at_top_level_hint(tmp_path):
    (tmp_path / "m.aa2mi").write_text("macro m { Notification(Local); }", encoding="utf-8")
    (tmp_path / "t.aa2mi").write_text(
        'trigger "tpl" { on CARD_ADDED; Notification(const("Local")); }', encoding="utf-8"
    )
    for library, use in (("m", "m();"), ("t", 'import.trigger "tpl" { }')):
        body = f'trigger "T" {{ on CARD_ADDED; {use} }}' if library == "m" else use
        source = f'import "{library}.aa2mi"; module "M" {{ const Local: string = "x"; {body} }}'
        with pytest.raises((SourceBindingError, SourceImportError)) as caught:
            parse_module(source, import_base=tmp_path)
        diagnostic = caught.value.diagnostic
        assert "not visible in macros or templates" in diagnostic.message
        assert diagnostic.help == "declare it at top level"


def test_top_level_constant_cannot_reference_a_module_constant():
    code, *_ = _error('const A: int = B; module "M" { const B: int = 1; }')
    assert code == "UNDEFINED_CONST"


def test_constant_declarations_count_against_the_node_budget():
    source = 'module "M" { const A: int = 1; const B: int = 2; }'
    with pytest.raises(SourceLimitError):
        parse_module(source, source_limits=SourceLimits(max_nodes=6))


def test_module_constants_feed_trigger_import_slot_actuals(tmp_path):
    (tmp_path / "t.aa2mi").write_text(
        'trigger "tpl" { slot N int; on CARD_ADDED; ThisCard.SetInt("n", N); }',
        encoding="utf-8",
    )
    constants = (
        'import "t.aa2mi"; module "M" { const Five: int = 5; import.trigger "tpl" { slot N = Five; '
        "} }"
    )
    literals = 'module "M" { trigger "tpl" { on CARD_ADDED; ThisCard.SetInt("n", 5); } }'
    assert parse_module(constants, import_base=tmp_path).to_ir() == parse_module(literals).to_ir()


# --- Reference forms: bare identifier versus const("...") ------------------------------


@pytest.mark.parametrize("declaration", ["const Limit: string = ", 'const "Limit": string = '])
def test_bare_name_and_const_call_are_equivalent_for_identifier_names(declaration):
    items = (
        f'{declaration}"v"; const Alias: string = Limit; const Alias2: string = const("Limit"); '
        'global g1: string = Limit; global g2: string = const("Limit");'
    )
    plain = 'global g1: string = "v"; global g2: string = "v";'
    bare = _module("Notification(Limit); Notification(Alias);", items)
    called = _module('Notification(const("Limit")); Notification(Alias2);', items)
    literal = _module('Notification("v"); Notification("v");', plain)
    _same(bare, literal)
    _same(called, literal)


@pytest.mark.parametrize("declaration", ["const Lead: int = 0;", 'const "Lead": int = 0;'])
def test_identifier_named_receiver_constants_accept_both_forms(declaration):
    literal = _module("(0).SetVirtue(3); let v: int = (0).Virtue;")
    _same(_module("Lead.SetVirtue(3); let v: int = Lead.Virtue;", declaration), literal)
    _same(
        _module('const("Lead").SetVirtue(3); let v: int = const("Lead").Virtue;', declaration),
        literal,
    )


def test_names_with_spaces_require_const_call():
    items = (
        'const "With Spaces": string = "x"; const "Lead Seat": int = 0; '
        'const Alias: string = const("With Spaces"); global g: string = const("With Spaces");'
    )
    literal = _module(
        'Notification("x"); Notification("x"); (0).SetVirtue(3);', 'global g: string = "x";'
    )
    use = (
        'Notification(const("With Spaces")); Notification(Alias); const("Lead Seat").SetVirtue(3);'
    )
    _same(_module(use, items), literal)
    # No bare spelling exists: the lexer sees two identifiers.
    broken = _module("Notification(With Spaces);", items)
    code, line, column = _error(broken)
    assert (code, line) == ("SYNTAX_ERROR", 1)
    assert column == broken.rindex("Spaces") + 1
    # variable("...") never reaches constants.
    code, *_ = _error(_module('Notification(variable("With Spaces"));', items))
    assert code == "UNDEFINED_VARIABLE"


def test_keyword_named_constant_is_reachable_only_through_const_call():
    items = 'const "true": bool = false;'
    use = 'if (true) { Notification("t"); } if (const("true")) { Notification("c"); }'
    literal = 'if (true) { Notification("t"); } if (false) { Notification("c"); }'
    _same(_module(use, items), _module(literal))


def test_const_call_never_resolves_variables():
    code, *_ = _error(_module('let X: int = 1; Notification(const("X"));'))
    assert code == "UNDEFINED_CONST"
