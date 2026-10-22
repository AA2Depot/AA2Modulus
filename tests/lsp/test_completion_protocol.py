"""Framed-server regressions for completion contexts and replacement edits."""

from __future__ import annotations


def _completion(client, uri, source, character, version=1):
    if version == 1:
        client.open(uri, source)
    else:
        client.change(uri, source, version)
    return client.request(
        "textDocument/completion",
        {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": character},
        },
    )


def test_stdio_completion_returns_readonly_members_and_full_midtoken_edit(client):
    uri = "untitled:CompletionMembers"
    source = 'module "M😀" { trigger "T" { let day: int = Globals.CurrentDay; } }'
    start = source.index("Globals.CurrentDay")
    cursor = start + len("Globals.Cur")
    # LSP positions count UTF-16 code units, so the emoji adds one extra unit.
    items = _completion(client, uri, source, cursor + 1)
    item = next(value for value in items if value["label"] == "Globals.CurrentDay")

    assert item["textEdit"]["newText"] == "Globals.CurrentDay"
    assert item["textEdit"]["range"] == {
        "start": {"line": 0, "character": start + 1},
        "end": {"line": 0, "character": start + len("Globals.CurrentDay") + 1},
    }


def test_stdio_initial_dot_response_supports_local_prefix_refinement(client):
    uri = "untitled:CompletionFilterText"
    source = 'module "M" { trigger "T" { let day: int = Globals.'
    items = _completion(client, uri, source, len(source))

    assert items
    assert all(item.get("filterText") == item["label"] for item in items)
    refined = [
        item
        for item in items
        if item.get("filterText", item["label"]).casefold().startswith("Globals.P".casefold())
    ]
    assert "Globals.PlayerCharacter" in {item["label"] for item in refined}


def test_stdio_completion_inside_existing_call_keeps_arguments_and_suffix(client):
    uri = "untitled:CompletionCall"
    source = 'module "M" { trigger "T" { Noti("keep", true); } }'
    start = source.index("Noti")
    items = _completion(client, uri, source, start + 2)
    item = next(value for value in items if value["label"] == "Notification")

    assert item["textEdit"]["newText"] == "Notification"
    assert item["textEdit"]["range"] == {
        "start": {"line": 0, "character": start},
        "end": {"line": 0, "character": start + len("Noti")},
    }


def test_framed_server_member_completion_and_signature_use_utf16_positions(snippet_client):
    uri = "untitled:ReceiverFramed"
    prefix = 'module "M😀" { trigger "T" { on CARD_ADDED; let actor: card = ThisCard; '
    source = prefix + "actor.AddLi"
    snippet_client.open(uri, source)
    units = len(source) + 1
    items = snippet_client.request(
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
    snippet_client.change(uri, source, 2)
    signature = snippet_client.request(
        "textDocument/signatureHelp",
        {"textDocument": {"uri": uri}, "position": {"line": 0, "character": len(source) + 1}},
    )
    assert signature["signatures"][0]["label"] == "AddLike(towards: card, amount: int)"
    assert signature["activeParameter"] == 0
