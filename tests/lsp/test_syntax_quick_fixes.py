"""Syntax errors publish together and their exact fixes are quick fixes."""

from __future__ import annotations

from tests.lsp.test_code_actions import _actions, _apply
from tests.support.lsp_client import Client

BROKEN = (
    'module "M" {\n  trigger "T" {\n    on CARD_ADDED;\n    let y: int = 1;\n'
    "    if y = 3 { }\n    y = ;\n  }\n}\n"
)
FIXED = BROKEN.replace("if y = 3", "if y == 3")


def test_two_syntax_errors_publish_and_the_equality_fix_clears_the_first(client: Client, tmp_path):
    uri = (tmp_path / "syntax.aa2m").as_uri()
    client.open(uri, BROKEN)
    diagnostics = client.diagnostics(uri, bool, version=1)

    assert [item["code"] for item in diagnostics] == ["SYNTAX_ERROR", "SYNTAX_ERROR"]
    assert [item["range"]["start"]["line"] for item in diagnostics] == [4, 5]
    assert "unexpected `=`" in diagnostics[0]["message"]
    assert "help: use `==` to compare" in diagnostics[0]["message"]

    (action,) = _actions(client, uri, [diagnostics[0]])
    assert action["title"] == "Use '=='"
    assert action["kind"] == "quickfix"
    assert action["diagnostics"] == [diagnostics[0]]
    fixed = _apply(BROKEN, action["edit"]["changes"][uri])
    assert fixed == FIXED
    assert _actions(client, uri, [diagnostics[1]]) == []

    client.change(uri, FIXED.replace("y = ;", 'WriteLog("x");'), 2)
    assert client.diagnostics(uri, version=2) == []


RECOVERED = (
    'module "Receiver" {\n  depends_on "Provider";\n\n  trigger "T" {\n    on CARD_ADDED;\n'
    '    raw_action 1(raw_expression int 2 { variable "counter"; }, 1);\n  }\n}\n'
)


def test_another_modules_global_is_declared_by_a_quick_fix(client: Client, tmp_path):
    uri = (tmp_path / "receiver.aa2m").as_uri()
    client.open(uri, RECOVERED)
    diagnostics = client.diagnostics(uri, bool, version=1)

    assert {item["code"] for item in diagnostics} == {"UNDEFINED_VARIABLE"}
    (action,) = _actions(client, uri, [diagnostics[0]])
    assert action["title"] == "Declare global 'counter'"
    fixed = _apply(RECOVERED, action["edit"]["changes"][uri])
    assert fixed == RECOVERED.replace(
        '  trigger "T"', '  global counter: int = 0;\n\n  trigger "T"'
    )

    client.change(uri, fixed, 2)
    assert client.diagnostics(uri, version=2) == []


RESERVED = 'module "M" {\n  trigger "T" {\n    on CARD_ADDED;\n    let import: int = 1;\n  }\n}\n'


def test_a_bare_reserved_declaration_is_quoted_by_a_quick_fix(client: Client, tmp_path):
    uri = (tmp_path / "reserved.aa2m").as_uri()
    client.open(uri, RESERVED)
    (diagnostic,) = client.diagnostics(uri, bool, version=1)

    assert diagnostic["code"] == "SYNTAX_ERROR"
    (action,) = _actions(client, uri, [diagnostic])
    assert action["title"] == "Write '\"import\"'"
    fixed = _apply(RESERVED, action["edit"]["changes"][uri])
    assert fixed == RESERVED.replace("let import", 'let "import"')

    client.change(uri, fixed, 2)
    assert client.diagnostics(uri, version=2) == []
