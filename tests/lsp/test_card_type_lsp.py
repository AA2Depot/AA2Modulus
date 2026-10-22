"""Protocol-visible editor behavior for source-only card types."""

from __future__ import annotations

from lsprotocol import types

from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.features.navigation import hover
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.signature.help import signature_help
from aa2modulus.lsp.workspace.documents import SourceWorkspace
from tests.support.lsp_client import Client
from tests.support.lsp_workspace import analyze_workspace


def _snapshot(source: str, context):
    workspace = SourceWorkspace()
    uri = "untitled:CardHover"
    workspace.open(uri, source, 1)
    return workspace, analyze_workspace(workspace, uri, context)


def _apply(source: str, edits: list[dict]) -> str:
    codec = PositionCodec(source)
    for edit in sorted(
        edits,
        key=lambda item: codec.offset(types.Position(**item["range"]["start"])),
        reverse=True,
    ):
        start = codec.offset(types.Position(**edit["range"]["start"]))
        end = codec.offset(types.Position(**edit["range"]["end"]))
        source = source[:start] + edit["newText"] + source[end:]
    return source


def test_card_declaration_and_builtin_hover_and_flat_signature(context):
    source = (
        'module "Cards" { trigger "T" { on CARD_ADDED; '
        "let coach: card = ThisCard; let target: card = Context.NpcTalkTarget; "
        "let filled: bool = Globals.IsSeatFilled(coach); } }"
    )
    _workspace, snapshot = _snapshot(source, context)
    codec = PositionCodec(source)

    declaration = hover(snapshot, codec.position(source.index("coach: card")), "utf-16")
    assert declaration is not None and "coach: card" in declaration.contents.value
    builtin = hover(snapshot, codec.position(source.index("NpcTalkTarget")), "utf-16")
    assert builtin is not None and "Returns: card" in builtin.contents.value

    call = source.index("Globals.IsSeatFilled(") + len("Globals.IsSeatFilled(")
    signature = signature_help(source[:call], call, context)
    assert signature is not None
    assert signature.signatures[0].label == "Globals.IsSeatFilled(seat: card)"


def test_card_argument_quick_fix_is_versioned_and_clears_diagnostic(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    client = Client(
        capabilities={"workspace": {"workspaceEdit": {"documentChanges": True}}},
        workspace_folders=[{"uri": root.as_uri(), "name": "cards"}],
    )
    try:
        uri = (root / "card.aa2m").as_uri()
        source = (
            'module "Cards" { trigger "T" { on CARD_ADDED; '
            "let amount: int = 4; let coach: card = ThisCard; "
            "coach.AddLike(amount, coach); } }"
        )
        fixed = source.replace("coach.AddLike(amount, coach)", "coach.AddLike(Card(amount), coach)")
        client.open(uri, source, version=1)
        (diagnostic,) = client.diagnostics(uri, bool, version=1)
        assert diagnostic["code"] == "SOURCE_TYPE_MISMATCH"
        assert "expected card, found int" in diagnostic["message"]

        (action,) = client.request(
            "textDocument/codeAction",
            {
                "textDocument": {"uri": uri},
                "range": diagnostic["range"],
                "context": {"diagnostics": [diagnostic], "only": ["quickfix"]},
            },
        )
        assert action["title"] == "Write Card(amount)"
        (change,) = action["edit"]["documentChanges"]
        assert change["textDocument"] == {"uri": uri, "version": 1}
        assert _apply(source, change["edits"]) == fixed

        client.change(uri, fixed, version=2)
        assert client.diagnostics(uri, version=2) == []
        assert (
            client.request(
                "textDocument/codeAction",
                {
                    "textDocument": {"uri": uri},
                    "range": diagnostic["range"],
                    "context": {"diagnostics": [diagnostic], "only": ["quickfix"]},
                },
            )
            == []
        )
        client.finish()
    finally:
        if client.process.poll() is None:
            client.process.terminate()
            client.process.wait(timeout=10)


def _ranked(source: str, context) -> list[str]:
    items = completions(source, len(source), context)
    return [item.label for item in sorted(items, key=lambda item: item.sort_text or item.label)]


def test_card_argument_completion_ranks_cards_without_filtering(context):
    prefix = (
        'macro Check { param seat card; } module "Cards" { trigger "T" { '
        "on CARD_ADDED; let coach: card = ThisCard; let amount: int = 4; "
    )
    contexts = (
        ("coach.AddLike(", {"coach", "ThisCard"}),
        ("let filled: bool = Globals.IsSeatFilled(", {"coach", "ThisCard"}),
        ("Check(", {"coach", "ThisCard"}),
    )
    for tail, expected_cards in contexts:
        source = prefix + tail
        labels = _ranked(source, context)
        card_positions = [labels.index(label) for label in expected_cards]
        integer_positions = [labels.index(label) for label in ("amount", "Globals.CurrentDay")]
        assert max(card_positions) < min(integer_positions), tail
        assert {"amount", "Globals.CurrentDay"} <= set(labels), tail
