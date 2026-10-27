"""Source formatting preserves the authored serialized state."""

from __future__ import annotations

import struct

import pytest

from aa2modulus.app.compile import compile_source
from aa2modulus.decompile.format.module import format_module
from aa2modulus.syntax.parser.errors import SourceParseError
from tests.support.source import parse_module


def test_formatted_source_preserves_module_defaults_globals_and_dependencies():
    source = """module "State" {
      description "Description";
      depends_on "DependencyA";
      global counter: int { default 0; current 1; initialized true; }
      trigger "Init" { on CARD_ADDED; let label: string = "ready"; Notification(label, true); }
    }"""
    module = parse_module(source)
    formatted = format_module(module)
    restored = parse_module(formatted)
    assert restored.to_ir() == module.to_ir()
    assert restored.globals[0].initialized is True
    assert restored.globals[0].current_value.value == 1
    assert restored.dependencies == ("DependencyA",)


# Edge patterns, then two ordinary values whose decimal spelling must keep the binary32 bits.
@pytest.mark.parametrize(
    "bits", (0x80000000, 0x00000001, 0x7F800000, 0x7FC00001, 0x7FA00001, 0x60AD78EC, 0x1E3CE508)
)
def test_source_float_bits_survive_formatting_and_compilation(bits):
    source = f'module "Float" {{ global value: float = float_bits(0x{bits:08x}); }}'
    # Native layout: name, description, triggers, one FLOAT global named value,
    # default/current payloads, initialized=false, empty dependencies.
    expected = bytes.fromhex(
        "05000000 46006c006f0061007400 00000000 00000000 01000000 "
        "03000000 05000000 760061006c0075006500"
    ) + struct.pack("<iIiIBI", 3, bits, 3, bits, 0, 0)
    assert compile_source(source) == expected
    assert compile_source(format_module(parse_module(source))) == expected


@pytest.mark.parametrize(
    "source, expected",
    (
        ('module "Branches" { trigger "T" { if true {} else {} } }', (2, 4)),
        ('module "Branches" { trigger "T" { ElseIf false {} Else; } }', (3, 4)),
    ),
)
def test_attached_and_standalone_branch_source_keeps_native_action_order(source, expected):
    assert (
        tuple(action.action.id for action in parse_module(source).triggers[0].gui_actions)
        == expected
    )


def test_branch_syntax_errors_report_the_offending_line_and_column():
    source = 'module "M" {\n  trigger "T" {\n    else {}\n  }\n}'
    with pytest.raises(SourceParseError) as raised:
        parse_module(source, filename="branch.aa2m")
    assert (raised.value.filename, raised.value.line, raised.value.column) == (
        "branch.aa2m",
        3,
        10,
    )


def test_named_constant_expression_projects_to_ir_by_constant_id():
    module = parse_module(
        'module "M" { trigger "T" { let x: int = Constants.Relationship.LOVE; } }'
    )
    expression = module.triggers[0].variables[0].default_expression
    assert expression.to_ir() == {"return_type": 1, "id": 3, "named_constant_id": 1}


def test_float_constants_project_to_ir_by_bits_when_unusual_and_by_value_otherwise():
    patterns = (0x80000000, 0x00000001, 0x7F800000, 0x7FC00001, 0x7FA00001)
    declarations = " ".join(
        f"global g{index}: float = float_bits(0x{bits:08x});" for index, bits in enumerate(patterns)
    )

    module = parse_module(f'module "M" {{ {declarations} global plain: float = 1.5; }}')

    assert [item.default_value.to_ir() for item in module.globals] == [
        *({"type": 3, "value": None, "float_bits": bits} for bits in patterns),
        {"type": 3, "value": 1.5},
    ]
