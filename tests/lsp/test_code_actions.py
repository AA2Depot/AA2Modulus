"""Quick fixes from published diagnostic data, applied through a protocol session."""

from __future__ import annotations

import pytest
from lsprotocol import types

from aa2modulus.lsp.protocol.positions import PositionCodec
from tests.support.lsp_client import Client

FLAT = 'module "M" { trigger "T" { on CARD_ADDED;\n  SetVirtue(ThisCard, 3);\n} }\n'
FIXED = 'module "M" { trigger "T" { on CARD_ADDED;\n  ThisCard.SetVirtue(3);\n} }\n'


def _apply(source: str, edits: list[dict]) -> str:
    codec = PositionCodec(source)
    for edit in sorted(
        edits, key=lambda item: codec.offset(_position(item["range"]["start"])), reverse=True
    ):
        start = codec.offset(_position(edit["range"]["start"]))
        end = codec.offset(_position(edit["range"]["end"]))
        source = source[:start] + edit["newText"] + source[end:]
    return source


def _position(value: dict) -> types.Position:
    return types.Position(value["line"], value["character"])


def _actions(client: Client, uri: str, diagnostics: list[dict], **context) -> list[dict]:
    return client.request(
        "textDocument/codeAction",
        {
            "textDocument": {"uri": uri},
            "range": diagnostics[0]["range"] if diagnostics else _zero(),
            "context": {"diagnostics": diagnostics, **context},
        },
    )


def _zero() -> dict:
    return {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}


@pytest.mark.parametrize("document_changes", (False, True))
def test_preferred_fix_rewrites_a_flat_call_and_clears_the_error(tmp_path, document_changes):
    capabilities = (
        {"workspace": {"workspaceEdit": {"documentChanges": True}}} if document_changes else None
    )
    client = Client(capabilities=capabilities)
    try:
        provider = client.initialized["capabilities"]["codeActionProvider"]
        assert provider == {"codeActionKinds": ["quickfix"]}
        uri = (tmp_path / "root.aa2m").as_uri()
        client.open(uri, FLAT)
        (diagnostic,) = client.diagnostics(uri, bool, version=1)
        assert diagnostic["code"] == "UNKNOWN_ACTION_NAME"
        assert "help: use 'ThisCard.SetVirtue(3)'" in diagnostic["message"]

        (action,) = _actions(client, uri, [diagnostic])
        assert action["title"] == "Write 'ThisCard.SetVirtue(3)'"
        assert action["kind"] == "quickfix"
        assert action["isPreferred"] is True
        assert action["diagnostics"] == [diagnostic]
        if document_changes:
            (change,) = action["edit"]["documentChanges"]
            assert change["textDocument"] == {"uri": uri, "version": 1}
            edits = change["edits"]
        else:
            edits = action["edit"]["changes"][uri]
        assert _apply(FLAT, edits) == FIXED

        # Only quick fixes are offered, and only for the version they were computed for.
        assert _actions(client, uri, [diagnostic], only=["refactor"]) == []
        client.change(uri, FIXED, 2)
        assert client.diagnostics(uri, version=2) == []
        assert _actions(client, uri, [diagnostic]) == []
        client.finish()
    finally:
        if client.process.poll() is None:
            client.process.terminate()
            client.process.wait(timeout=10)


def test_fixes_cover_roots_protected_names_and_none_for_advice(client, tmp_path):
    uri = (tmp_path / "fixes.aa2m").as_uri()
    cases = (
        (
            'module "M" { trigger "T" { on CARD_ADDED; let a: int = globals.CurrentDay; } }',
            ["Change 'globals' to 'Globals'"],
            'module "M" { trigger "T" { on CARD_ADDED; let a: int = Globals.CurrentDay; } }',
        ),
        (
            'module "M" { global "ThisCard": int = 0; trigger "T" { on CARD_ADDED; ThisCard = 3; '
            "} }",
            ['Write variable("ThisCard")'],
            (
                'module "M" { global "ThisCard": int = 0; '
                'trigger "T" { on CARD_ADDED; variable("ThisCard") = 3; } }'
            ),
        ),
        ('module "M" { trigger "T" { on CARD_ADDED; Missing(); } }', [], None),
    )
    for version, (source, titles, fixed) in enumerate(cases, 1):
        if version == 1:
            client.open(uri, source)
        else:
            client.change(uri, source, version)
        (diagnostic,) = client.diagnostics(uri, bool, version=version)
        assert ("data" in diagnostic) == bool(titles)
        actions = _actions(client, uri, [diagnostic])
        assert [item["title"] for item in actions] == titles
        if fixed is not None:
            assert _apply(source, actions[0]["edit"]["changes"][uri]) == fixed
