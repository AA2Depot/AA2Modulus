"""Comments and line endings do not change authored source behavior."""

from __future__ import annotations

from pathlib import Path

from aa2modulus.app.compile import compile_source
from aa2modulus.binary.reader import decode_module


def test_comments_between_macro_tokens_in_crlf_library_and_call_expand_normally(tmp_path: Path):
    library = tmp_path / "messages.aa2mi"
    library.write_text(
        '/* library */ macro/* after keyword */ "write" {\r\n'
        '  param/* name */ "message"/* type */ string;\r\n'
        "  WriteLog(message); // end of definition\r\n"
        "}\r\n",
        encoding="utf-8",
        newline="",
    )
    source = (
        'import "messages.aa2mi"; // imported macro\r\n'
        'module "M" {\r\n'
        '  trigger "T" { write/* call */("hello"); }\r\n'
        "}\r\n"
    )
    expected = 'module "M" { trigger "T" { WriteLog("hello"); } }'
    assert compile_source(source, filename="root.aa2m", import_base=tmp_path) == compile_source(
        expected
    )


def test_keyword_prefix_names_remain_identifiers_around_branch_syntax():
    source = """module "Names" {
      trigger "T" {
        let Elsewhere: bool = false;
        let ElseIfFlag: bool = true;
        if Elsewhere || ElseIfFlag {} else {}
      }
    }"""
    trigger = decode_module(compile_source(source)).module.triggers[0]
    assert [
        (variable.name, variable.default_expression.constant.value)
        for variable in trigger.variables
    ] == [
        ("Elsewhere", False),
        ("ElseIfFlag", True),
    ]
    assert tuple(node.action.id for node in trigger.gui_actions) == (2, 4)
    condition = trigger.gui_actions[0].action.parameters[0]
    assert (condition.return_type, condition.id) == (2, 5)
    assert tuple(operand.variable_name for operand in condition.parameters) == (
        "Elsewhere",
        "ElseIfFlag",
    )
