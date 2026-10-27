"""Compile-time source constants substitute literals and never reach SIR or the binary."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source
from aa2modulus.app.decompile import decompile_module
from aa2modulus.context.limits import SourceLimits
from tests.support.source import assert_same_binary, module_source, parse_module


def _error(source: str, **kwargs):
    error = validate_source(source, **kwargs).errors[0]
    return error.code, error.line, error.column


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
    binary = assert_same_binary(OWNER_EXAMPLE, OWNER_LITERALS)
    decompiled = decompile_module(binary).source
    assert "const" not in decompiled
    assert "Test Module With Spaces" in decompiled


def test_references_chain_in_any_order_and_unused_constants_emit_nothing():
    constants = module_source(
        "Notification(B);",
        'const B: string = const("A"); const A: string = "hi"; const Unused: int = 3;',
    )
    assert_same_binary(constants, module_source('Notification("hi");'))


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
    assert_same_binary(module_source(use, items), module_source(plain))


def test_float_bits_constant_keeps_exact_bits():
    items = "const F: float = float_bits(0x7fc00001);"
    use = 'ThisCard.SetFloat("f", F);'
    assert_same_binary(
        module_source(use, items), module_source('ThisCard.SetFloat("f", float_bits(0x7fc00001));')
    )


def test_global_initializer_accepts_constants_but_state_form_stays_literal():
    items = 'const Start: int = 7; global a: int = Start; global b: int = const("Start");'
    assert_same_binary(
        module_source("", items),
        module_source("", "global a: int = 7; global b: int = 7;"),
    )
    state_form = (
        "const Start: int = 7; global a: int { default Start; current 1; initialized true; }"
    )
    assert _error(module_source("", state_form))[0] == "SYNTAX_ERROR"


def test_quoted_keyword_like_names_and_prefix_identifiers_are_ordinary():
    items = (
        'const "int": string = "a"; const "if": string = "b"; const const_x: string = "c"; '
        'const "constant": string = "d"; const constant_x: string = "e";'
    )
    use = (
        'Notification(const("int")); Notification(const("if")); Notification(const_x); '
        'Notification(const("constant")); Notification(constant_x);'
    )
    plain = (
        'Notification("a"); Notification("b"); Notification("c"); Notification("d"); '
        'Notification("e");'
    )
    assert_same_binary(module_source(use, items), module_source(plain))


def test_raw_constant_payload_and_const_prefixed_identifiers_still_parse():
    source = module_source(
        "let constant_x: int = raw_expression int 1 { constant 4; }; let const_y: int = constant_x;"
    )
    first, second = parse_module(source).triggers[0].variables
    assert (first.name, first.default_expression.constant.value) == ("constant_x", 4)
    assert (second.name, second.default_expression.variable_name) == ("const_y", "constant_x")


@pytest.mark.parametrize(
    ("body", "items"),
    [
        ("let const: int = 1;", ""),
        ("const = 1;", ""),
        ("on const;", ""),
        ("", "global const: int = 1;"),
    ],
)
def test_const_is_not_an_identifier(body, items):
    assert _error(module_source(body, items))[0] == "SYNTAX_ERROR"


def test_global_trigger_and_local_names_may_still_be_quoted_const():
    module = parse_module(
        'module "M" { global "const": int = 1; trigger "const" { let "const": int = 2; } }'
    )
    assert module.globals[0].name == "const"
    assert module.triggers[0].name == "const"
    assert module.triggers[0].variables[0].name == "const"


def test_variable_forms_never_resolve_constants():
    items = "const K: int = 1;"
    assert _error(module_source('let x: int = variable("K");', items))[0] == "UNDEFINED_VARIABLE"
    assert _error(module_source('variable("K") = 2;', items))[0] == "UNDEFINED_VARIABLE"
    raw = 'let x: int = raw_expression int 2 { variable "K"; };'
    # A raw variable payload names a variable only; no constant is substituted.
    expression = parse_module(module_source(raw, items)).triggers[0].variables[0].default_expression
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
    source = module_source('ThisCard.SetInt("k", K);', 'const K: string = "s";')
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
    source = module_source('Notification(const("Missing"));')
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
    assert_same_binary(constants, literals, import_base=tmp_path)


def test_distinct_library_definitions_with_one_name_fail_even_unused(tmp_path):
    (tmp_path / "a.aa2mi").write_text("const K: int = 1;", encoding="utf-8")
    (tmp_path / "b.aa2mi").write_text("const K: int = 2;", encoding="utf-8")
    source = 'import "a.aa2mi"; import "b.aa2mi"; module "M" { }'
    assert _error(source, import_base=tmp_path)[0] == "DUPLICATE_CONST"


@pytest.mark.parametrize(
    ("library", "use", "code"),
    [
        ("macro m { Notification(Local); }", "m();", "UNKNOWN_EXPRESSION_NAME"),
        (
            'trigger "tpl" { on CARD_ADDED; Notification(const("Local")); }',
            'import.trigger "tpl" { }',
            "UNDEFINED_CONST",
        ),
    ],
    ids=["macro", "template"],
)
def test_module_constants_are_not_visible_in_libraries_and_hint_to_declare_at_top_level(
    library, use, code, tmp_path
):
    (tmp_path / "lib.aa2mi").write_text(library, encoding="utf-8")
    body = f'trigger "T" {{ on CARD_ADDED; {use} }}' if use == "m();" else use
    source = f'import "lib.aa2mi"; module "M" {{ const Local: string = "x"; {body} }}'
    error = validate_source(source, import_base=tmp_path).errors[0]
    assert error.code == code
    assert error.filename == str((tmp_path / "lib.aa2mi").resolve())
    assert "not visible in macros or templates" in error.message
    assert error.help == "declare it at top level"


def test_top_level_constant_cannot_reference_a_module_constant():
    code, *_ = _error('const A: int = B; module "M" { const B: int = 1; }')
    assert code == "UNDEFINED_CONST"


def test_constant_declarations_count_against_the_node_budget():
    source = 'module "M" { const A: int = 1; const B: int = 2; }'
    assert _error(source, source_limits=SourceLimits(max_nodes=6))[0] == "SOURCE_NODE_LIMIT"


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
    assert_same_binary(constants, literals, import_base=tmp_path)


# --- Reference forms: bare identifier versus const("...") ------------------------------


@pytest.mark.parametrize("declaration", ["const Limit: string = ", 'const "Limit": string = '])
def test_bare_name_and_const_call_are_equivalent_for_identifier_names(declaration):
    items = (
        f'{declaration}"v"; const Alias: string = Limit; const Alias2: string = const("Limit"); '
        'global g1: string = Limit; global g2: string = const("Limit");'
    )
    plain = 'global g1: string = "v"; global g2: string = "v";'
    bare = module_source("Notification(Limit); Notification(Alias);", items)
    called = module_source('Notification(const("Limit")); Notification(Alias2);', items)
    literal = module_source('Notification("v"); Notification("v");', plain)
    assert_same_binary(bare, literal)
    assert_same_binary(called, literal)


@pytest.mark.parametrize("declaration", ["const Lead: int = 0;", 'const "Lead": int = 0;'])
def test_identifier_named_receiver_constants_accept_both_forms(declaration):
    literal = module_source("(0).SetVirtue(3); let v: int = (0).Virtue;")
    assert_same_binary(
        module_source("Lead.SetVirtue(3); let v: int = Lead.Virtue;", declaration), literal
    )
    assert_same_binary(
        module_source(
            'const("Lead").SetVirtue(3); let v: int = const("Lead").Virtue;', declaration
        ),
        literal,
    )


def test_names_with_spaces_require_const_call():
    items = (
        'const "With Spaces": string = "x"; const "Lead Seat": int = 0; '
        'const Alias: string = const("With Spaces"); global g: string = const("With Spaces");'
    )
    literal = module_source(
        'Notification("x"); Notification("x"); (0).SetVirtue(3);', 'global g: string = "x";'
    )
    use = (
        'Notification(const("With Spaces")); Notification(Alias); const("Lead Seat").SetVirtue(3);'
    )
    assert_same_binary(module_source(use, items), literal)
    # No bare spelling exists: the lexer sees two identifiers.
    broken = module_source("Notification(With Spaces);", items)
    code, line, column = _error(broken)
    assert (code, line) == ("SYNTAX_ERROR", 1)
    assert column == broken.rindex("Spaces") + 1
    # variable("...") never reaches constants.
    code, *_ = _error(module_source('Notification(variable("With Spaces"));', items))
    assert code == "UNDEFINED_VARIABLE"


def test_keyword_named_constant_is_reachable_only_through_const_call():
    items = 'const "true": bool = false;'
    use = 'if (true) { Notification("t"); } if (const("true")) { Notification("c"); }'
    literal = 'if (true) { Notification("t"); } if (false) { Notification("c"); }'
    assert_same_binary(module_source(use, items), module_source(literal))


def test_const_call_never_resolves_variables():
    code, *_ = _error(module_source('let X: int = 1; Notification(const("X"));'))
    assert code == "UNDEFINED_CONST"
