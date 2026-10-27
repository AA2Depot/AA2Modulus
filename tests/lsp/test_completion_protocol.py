"""Completion over stdio: UTF-16 positions in and out, and the language ID of untitled libraries."""

from __future__ import annotations


def test_member_completion_and_signature_use_utf16_positions(full_client):
    uri = "untitled:ReceiverFramed"
    prefix = 'module "M😀" { trigger "T" { on CARD_ADDED; let actor: card = ThisCard; '
    source = prefix + "actor.AddLi"
    full_client.open(uri, source)
    units = len(source) + 1
    items = full_client.request(
        "textDocument/completion",
        {"textDocument": {"uri": uri}, "position": {"line": 0, "character": units}},
    )
    item = next(value for value in items if value["label"] == "AddLike")

    assert [value["label"] for value in items] == ["AddLike"]
    assert item["textEdit"]["newText"] == "AddLike(${1:towards}, ${2:amount});$0"
    assert item["textEdit"]["range"] == {
        "start": {"line": 0, "character": len(prefix + "actor.") + 1},
        "end": {"line": 0, "character": units},
    }
    assert item["insertTextFormat"] == 2

    source = prefix + "actor.AddLike("
    full_client.change(uri, source, 2)
    signature = full_client.request(
        "textDocument/signatureHelp",
        {"textDocument": {"uri": uri}, "position": {"line": 0, "character": len(source) + 1}},
    )
    assert signature["signatures"][0]["label"] == "AddLike(towards: card, amount: int)"
    assert signature["activeParameter"] == 0


def test_untitled_library_gets_the_library_starter(full_client):
    uri = "untitled:Library"
    full_client.open(uri, "", language_id="aa2mi")
    items = full_client.request(
        "textDocument/completion",
        {"textDocument": {"uri": uri}, "position": {"line": 0, "character": 0}},
    )
    labels = {item["label"] for item in items}

    assert min(items, key=lambda item: item["sortText"])["label"] == "library"
    assert "module" not in labels
