"""Framed stdio sessions for references, highlights, rename and the workspace scan."""

from __future__ import annotations

from lsprotocol import types

from tests.support.lsp_client import Client

LIBRARY = "macro say { param message string; WriteLog(message); }\n"
ROOT = 'import "library.aa2mi";\nmodule "Root" { trigger "T" { on CARD_ADDED; say("root"); } }\n'
OTHER = 'import "library.aa2mi";\nmodule "Other" { trigger "T" { on CARD_ADDED; say("other"); } }\n'


def _position(source: str, needle: str) -> dict[str, int]:
    before = source[: source.index(needle)]
    return {"line": before.count("\n"), "character": len(before) - (before.rfind("\n") + 1)}


def _references(client: Client, uri: str, source: str, needle: str, **extra) -> list[str]:
    result = client.request(
        "textDocument/references",
        {
            "textDocument": {"uri": uri},
            "position": _position(source, needle),
            "context": {"includeDeclaration": True},
            **extra,
        },
    )
    return sorted(
        f"{item['uri'].rsplit('/', 1)[-1]}:{item['range']['start']['line']}" for item in result
    )


def test_server_registers_a_watcher_for_workspace_sources(full_client):
    (item,) = full_client.registration["registrations"]

    assert item["method"] == types.WORKSPACE_DID_CHANGE_WATCHED_FILES
    assert item["registerOptions"]["watchers"] == [{"globPattern": "**/*.{aa2m,aa2mi}"}]


def test_workspace_references_follow_closed_files_and_watched_events(full_client, tmp_path):
    client = full_client
    (tmp_path / "library.aa2mi").write_text(LIBRARY, encoding="utf-8")
    (tmp_path / "root.aa2m").write_text(ROOT, encoding="utf-8")
    (tmp_path / "other.aa2m").write_text(OTHER, encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "skipped.aa2m").write_text(
        OTHER.replace('"library.aa2mi"', '"../library.aa2mi"'), encoding="utf-8"
    )
    with client.folder(tmp_path, "mods"):
        root = (tmp_path / "root.aa2m").as_uri()
        client.open(root, ROOT)
        assert _references(client, root, ROOT, "say(", workDoneToken="scan") == [
            "library.aa2mi:0",
            "other.aa2m:1",
            "root.aa2m:1",
        ]
        progress = client.wait(
            lambda message: (
                message.get("method") == "$/progress"
                and message["params"]["token"] == "scan"
                and message["params"]["value"]["kind"] == "end"
            )
        )
        assert progress["params"]["token"] == "scan"

        third = tmp_path / "third.aa2m"
        third.write_text(OTHER.replace('"Other"', '"Third"'), encoding="utf-8")
        (tmp_path / "other.aa2m").write_text(OTHER.replace('say("other");', ""), encoding="utf-8")
        client.send(
            "workspace/didChangeWatchedFiles",
            {
                "changes": [
                    {"uri": third.as_uri(), "type": types.FileChangeType.Created.value},
                    {
                        "uri": (tmp_path / "other.aa2m").as_uri(),
                        "type": types.FileChangeType.Changed.value,
                    },
                ]
            },
        )
        assert _references(client, root, ROOT, "say(") == [
            "library.aa2mi:0",
            "root.aa2m:1",
            "third.aa2m:1",
        ]
        highlights = client.request(
            "textDocument/documentHighlight",
            {"textDocument": {"uri": root}, "position": _position(ROOT, "say(")},
        )
        assert [item["kind"] for item in highlights] == [types.DocumentHighlightKind.Read.value]

        third.unlink()
        client.send(
            "workspace/didChangeWatchedFiles",
            {"changes": [{"uri": third.as_uri(), "type": types.FileChangeType.Deleted.value}]},
        )
        assert _references(client, root, ROOT, "say(") == ["library.aa2mi:0", "root.aa2m:1"]


def test_rename_returns_versioned_edits_for_open_and_closed_files(full_client, tmp_path):
    client = full_client
    (tmp_path / "library.aa2mi").write_text(LIBRARY, encoding="utf-8")
    (tmp_path / "root.aa2m").write_text(ROOT, encoding="utf-8")
    (tmp_path / "other.aa2m").write_text(OTHER, encoding="utf-8")
    with client.folder(tmp_path, "mods"):
        root = (tmp_path / "root.aa2m").as_uri()
        client.open(root, ROOT, version=4)
        point = {"textDocument": {"uri": root}, "position": _position(ROOT, "say(")}
        prepared = client.request("textDocument/prepareRename", point)
        assert prepared["placeholder"] == "say"
        edit = client.request("textDocument/rename", {**point, "newName": "announce"})
        changes = {
            item["textDocument"]["uri"].rsplit("/", 1)[-1]: (
                item["textDocument"]["version"],
                [change["newText"] for change in item["edits"]],
            )
            for item in edit["documentChanges"]
        }
        assert changes == {
            "library.aa2mi": (None, ["announce"]),
            "root.aa2m": (4, ["announce"]),
            "other.aa2m": (None, ["announce"]),
        }

        error = client.request_error(
            "textDocument/prepareRename",
            {"textDocument": {"uri": root}, "position": _position(ROOT, "CARD_ADDED")},
        )
        assert error["code"] == types.LSPErrorCodes.RequestFailed.value


def test_global_rename_warns_and_refusals_are_request_failures(full_client):
    client = full_client
    uri = "untitled:Globals"
    source = 'module "M" { global flag: int = 1; trigger "T" { on CARD_ADDED; flag = 2; } }'
    client.open(uri, source)
    point = {"textDocument": {"uri": uri}, "position": _position(source, "flag = 2")}
    edit = client.request("textDocument/rename", {**point, "newName": "enabled"})
    (document,) = edit["documentChanges"]
    assert document["textDocument"] == {"uri": uri, "version": 1}
    assert [item["newText"] for item in document["edits"]] == ["enabled", "enabled"]
    warning = client.wait(
        lambda message: (
            message.get("method") == "window/showMessage"
            and "serialized variable name" in message["params"]["message"]
        )
    )
    assert warning["params"]["type"] == types.MessageType.Warning.value

    error = client.request_error("textDocument/rename", {**point, "newName": "TriggeringCard"})
    assert error["code"] == types.LSPErrorCodes.RequestFailed.value
