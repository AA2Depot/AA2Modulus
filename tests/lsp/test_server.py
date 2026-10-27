"""Real framed stdio sessions exercise the shared CLI and editor lifetime."""

from __future__ import annotations

import re

import pytest

from aa2modulus.version import __version__


def test_initialize_result_advertises_the_server_features(client, context):
    assert client.initialized["serverInfo"] == {"name": "aa2modulus", "version": __version__}
    capabilities = client.initialized["capabilities"]
    assert capabilities["positionEncoding"] == "utf-16"
    assert capabilities["textDocumentSync"] == {
        "openClose": True,
        "change": 2,
        "save": {"includeText": False},
    }
    assert capabilities["completionProvider"] == {"triggerCharacters": ["."]}
    assert capabilities["signatureHelpProvider"] == {"triggerCharacters": ["(", ","]}
    assert capabilities["codeActionProvider"] == {"codeActionKinds": ["quickfix"]}
    assert capabilities["documentLinkProvider"] == {"resolveProvider": False}
    assert capabilities["workspaceSymbolProvider"] == {"resolveProvider": False}
    assert capabilities["inlayHintProvider"] == {"resolveProvider": False}
    assert capabilities["executeCommandProvider"] == {
        "commands": ["aa2modulus.compileDocument", "aa2modulus.decompileModule"]
    }
    for provider in (
        "hoverProvider",
        "definitionProvider",
        "referencesProvider",
        "documentHighlightProvider",
        "documentSymbolProvider",
        "renameProvider",
    ):
        assert capabilities[provider] is True, provider
    assert "documentFormattingProvider" not in capabilities
    assert "range" not in capabilities["semanticTokensProvider"]
    assert capabilities["semanticTokensProvider"]["full"] is True
    # Earlier legend indices stay the same; new types are appended.
    assert capabilities["semanticTokensProvider"]["legend"] == {
        "tokenTypes": [
            "namespace",
            "function",
            "method",
            "property",
            "enumMember",
            "event",
            "variable",
            "parameter",
            "macro",
            "class",
            "keyword",
            "type",
            "number",
            "string",
            "comment",
            "operator",
            "decorator",
        ],
        "tokenModifiers": ["declaration", "readonly", "defaultLibrary", "modification"],
    }
    # Without client support there are no built-in pages or snippets; lexical tokens need none.
    syntax = capabilities["experimental"]["aa2modulus"]["syntax"]
    assert re.fullmatch(r"[0-9a-f]{64}", syntax["fingerprint"])
    assert capabilities["experimental"] == {
        "aa2modulus": {
            "contractVersion": 2,
            "syntax": {
                "version": context.source_policy.language_version,
                "fingerprint": syntax["fingerprint"],
            },
            "lexicalTokens": True,
        }
    }
    assert "textDocumentContent" not in capabilities["workspace"]


def test_open_edit_and_navigation_round_trip_publishes_versioned_diagnostics(client):
    uri = "untitled:Example"
    source = 'module "M" { global x: int = 1; trigger "T" { WriteLog(x.FullName); } }'
    client.open(uri, source)
    symbol = client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    assert symbol[0]["name"] == "M"
    assert [item["name"] for item in symbol[0]["children"]] == ["x", "T"]
    point = {"line": 0, "character": source.index("x.FullName")}
    result = client.request(
        "textDocument/definition", {"textDocument": {"uri": uri}, "position": point}
    )
    assert result == [
        {
            "uri": uri,
            "range": {"start": {"line": 0, "character": 20}, "end": {"line": 0, "character": 21}},
        }
    ]
    hover = client.request("textDocument/hover", {"textDocument": {"uri": uri}, "position": point})
    assert "x: int" in hover["contents"]["value"]

    bad = 'module "M" { trigger "T" { Missing(); } }'
    client.change(uri, bad, 2)
    errors = client.diagnostics(uri, bool, version=2)
    assert [item["code"] for item in errors] == ["UNKNOWN_ACTION_NAME"]
    assert errors[0]["severity"] == 1
    assert errors[0]["range"] == {
        "start": {"line": 0, "character": 27},
        "end": {"line": 0, "character": 37},
    }
    assert (
        client.request("textDocument/definition", {"textDocument": {"uri": uri}, "position": point})
        == []
    )
    several = 'module "M" { trigger "T" { Missing(); Other(); } }'
    client.change(uri, several, 3)
    errors = client.diagnostics(uri, lambda items: len(items) == 2, version=3)
    assert [item["range"]["start"]["character"] for item in errors] == [27, 38]


def test_incomplete_completion_signature_and_latest_version_after_cancellation(client):
    uri = "untitled:Incomplete"
    source = 'module "M" { trigger "T" { Noti'
    client.open(uri, source)
    params = {"textDocument": {"uri": uri}, "position": {"line": 0, "character": len(source)}}
    canceled = client.request_canceled("textDocument/hover", params)
    assert canceled["error"]["code"] == -32800
    items = client.request("textDocument/completion", params)
    assert any(item["label"] == "Notification" for item in items)
    source = 'module "M" { trigger "T" { Notification('
    client.change(uri, source, 2)
    params["position"]["character"] = len(source)
    signature = client.request("textDocument/signatureHelp", params)
    assert (
        signature["signatures"][0]["label"]
        == "Notification(text: string, isImportant: bool = false)"
    )
    client.change(uri, 'module "M" { @ }', 3)
    client.change(uri, 'module "M" {}', 4)
    symbols = client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    assert symbols[0]["name"] == "M"
    assert client.diagnostics(uri, lambda items: not items, version=4) == []


def _edit_after_an_emoji(connection, uri, character):
    """Retype the declared type with two ranges counted from the emoji in the module name."""

    source = 'module "😀" { global x: int = 1; }'
    connection.open(uri, source)
    connection.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    connection.send(
        "textDocument/didChange",
        {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [
                {
                    "range": {
                        "start": {"line": 0, "character": character},
                        "end": {"line": 0, "character": character + 3},
                    },
                    "text": "string",
                },
                {
                    "range": {
                        "start": {"line": 0, "character": character + 9},
                        "end": {"line": 0, "character": character + 10},
                    },
                    "text": '"updated"',
                },
            ],
        },
    )
    symbols = connection.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    assert symbols[0]["children"][0]["detail"] == "x: string"
    assert connection.diagnostics(uri, lambda items: not items, version=2) == []


def test_default_utf16_positions_drive_incremental_edits(client):
    _edit_after_an_emoji(client, "untitled:Unicode-utf-16", 24)


@pytest.mark.parametrize("encoding,character", [("utf-8", 26), ("utf-32", 23)])
def test_negotiated_positions_drive_incremental_edits(start_client, encoding, character):
    connection = start_client([encoding])
    assert connection.initialized["capabilities"]["positionEncoding"] == encoding
    _edit_after_an_emoji(connection, f"untitled:Unicode-{encoding}", character)


def test_import_owners_refresh_from_buffers_disk_and_close(client, tmp_path):
    library = tmp_path / "lib.aa2mi"
    library.write_text("macro emit { Missing(); }", encoding="utf-8")
    roots = [(tmp_path / f"{name}.aa2m").as_uri() for name in ("one", "two")]
    for uri in roots:
        client.open(
            uri,
            'import "lib.aa2mi"; module "M" { trigger "T" { on CARD_ADDED; emit(); } }',
        )
        client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    errors = client.diagnostics(
        library.as_uri(),
        lambda items: bool(items) and len(items[0].get("relatedInformation", [])) == 2,
    )
    assert len(errors) == 1
    (diagnostic,) = errors
    assert diagnostic["code"] == "UNKNOWN_ACTION_NAME"
    assert diagnostic["severity"] == 1
    assert diagnostic["range"] == {
        "start": {"line": 0, "character": 13},
        "end": {"line": 0, "character": 23},
    }
    related = diagnostic["relatedInformation"]
    assert {item["location"]["uri"] for item in related} == set(roots)
    assert all(item["message"] for item in related)
    client.send("textDocument/didClose", {"textDocument": {"uri": roots[0]}})
    assert client.diagnostics(library.as_uri(), bool)
    client.open(library.as_uri(), 'macro emit { Notification("buffer"); }')
    client.request("textDocument/documentSymbol", {"textDocument": {"uri": roots[1]}})
    assert client.diagnostics(library.as_uri(), lambda items: not items) == []
    client.send("textDocument/didClose", {"textDocument": {"uri": library.as_uri()}})
    assert client.diagnostics(library.as_uri(), bool)
    library.write_text('macro emit { Notification("disk fixed"); }', encoding="utf-8")
    client.send("textDocument/didSave", {"textDocument": {"uri": roots[1]}})
    assert client.diagnostics(library.as_uri(), lambda items: not items) == []
    client.send("textDocument/didClose", {"textDocument": {"uri": roots[1]}})
    assert client.diagnostics(roots[1], lambda items: not items) == []


def test_closed_files_keep_diagnostics_until_deleted(client, tmp_path):
    broken = tmp_path / "broken.aa2m"
    source = 'module "M" { global big: int = 9999999999999; }'
    broken.write_text(source, encoding="utf-8")
    uri = broken.as_uri()
    client.open(uri, source)
    (error,) = client.diagnostics(uri, bool)
    client.forget(lambda message: _is_published(message, uri))

    client.send("textDocument/didClose", {"textDocument": {"uri": uri}})
    assert client.diagnostics(uri) == [error]
    other = (tmp_path / "other.aa2m").as_uri()
    client.open(other, 'module "Other" {}')
    client.request("textDocument/documentSymbol", {"textDocument": {"uri": other}})
    assert client.diagnostics(other) == []
    # Unchanged diagnostics of the closed file are not sent again.
    assert not _published(client, uri)
    assert client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}}) == []

    broken.unlink()
    assert client.diagnostics(uri, lambda items: not items) == []


def test_did_save_republishes_import_diagnostics(client, tmp_path):
    library = tmp_path / "lib.aa2mi"
    root = tmp_path / "root.aa2m"
    library.write_text("macro emit { Missing(); }", encoding="utf-8")
    library_uri = library.as_uri()
    root_uri = root.as_uri()
    client.open(root_uri, 'import "lib.aa2mi"; module "M" { trigger "T" { emit(); } }')
    client.request("textDocument/documentSymbol", {"textDocument": {"uri": root_uri}})
    (diagnostic,) = client.diagnostics(library_uri, bool)
    assert diagnostic["code"] == "UNKNOWN_ACTION_NAME"
    library.write_text("macro emit { Other(); }", encoding="utf-8")
    client.send("textDocument/didSave", {"textDocument": {"uri": root_uri}})
    refreshed = client.diagnostics(library_uri, lambda items: "Other" in str(items))
    assert refreshed[0]["code"] == "UNKNOWN_ACTION_NAME"
    assert refreshed[0]["severity"] == 1


def test_edits_keep_diagnostics_until_reanalysis(client):
    uri = "untitled:Flicker"
    client.open(uri, 'module "M" { global big: int = 9999999999999; }')
    (error,) = client.diagnostics(uri, bool)
    client.change(uri, 'module "M" { global big: int = 99999999999999; }', 2)
    (updated,) = client.diagnostics(uri, version=2)
    assert updated["code"] == error["code"]
    # No empty list was published between the edit and the new analysis.
    assert not _published(client, uri)


def _is_published(message, uri):
    return (
        message.get("method") == "textDocument/publishDiagnostics"
        and message["params"]["uri"] == uri
    )


def _published(client, uri):
    return [message for message in client.saved if _is_published(message, uri)]


def test_aa2mi_can_be_opened_as_an_edited_library(client, tmp_path):
    uri = (tmp_path / "edited.aa2mi").as_uri()
    source = (
        'macro "say" { param "message" string; WriteLog(message); }\ntrigger "Welcome" { slot '
        '"greeting" string; on CARD_ADDED; WriteLog(greeting); }'
    )
    client.open(uri, source, language_id="aa2mi")
    symbols = client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    assert [item["name"] for item in symbols] == ["say", "Welcome"]
    assert client.diagnostics(uri, lambda items: not items, version=1) == []
    edited = source.replace('macro "say"', 'macro "speak"')
    client.change(uri, edited, 2)
    symbols = client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    assert [item["name"] for item in symbols] == ["speak", "Welcome"]
    assert client.diagnostics(uri, lambda items: not items, version=2) == []


def test_unknown_and_closed_uris_return_empty_authoring_results(client):
    uri = "untitled:Unknown"
    params = {"textDocument": {"uri": uri}, "position": {"line": 0, "character": 0}}
    assert client.request("textDocument/completion", params) == []
    assert client.request("textDocument/definition", params) == []
    assert client.request("textDocument/hover", params) is None
    client.open(uri, 'module "M" {}')
    client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
    client.send("textDocument/didClose", {"textDocument": {"uri": uri}})
    assert client.request("textDocument/completion", params) == []
    assert client.request("textDocument/definition", params) == []
    assert client.request("textDocument/hover", params) is None
