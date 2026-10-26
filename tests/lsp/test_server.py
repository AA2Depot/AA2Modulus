"""Real framed stdio sessions exercise the shared CLI and editor lifetime."""

from __future__ import annotations

import pytest

from aa2modulus.syntax.lexicon import source_lexicon
from aa2modulus.version import __version__
from tests.support.lsp_client import Client


def test_stdio_capabilities_navigation_and_diagnostic_parity(client, context):
    assert client.initialized["serverInfo"] == {"name": "aa2modulus", "version": __version__}
    capabilities = client.initialized["capabilities"]
    assert capabilities["positionEncoding"] == "utf-16"
    assert capabilities["textDocumentSync"]["change"] == 2
    # Without client textDocumentContent support there are no built-in pages.
    syntax = {
        "version": context.source_policy.language_version,
        "fingerprint": source_lexicon().fingerprint,
    }
    assert capabilities["experimental"] == {"aa2modulus": {"contractVersion": 1, "syntax": syntax}}
    assert "textDocumentContent" not in capabilities.get("workspace", {})
    assert all(
        capabilities[key]
        for key in (
            "hoverProvider",
            "definitionProvider",
            "documentSymbolProvider",
            "completionProvider",
            "signatureHelpProvider",
            "referencesProvider",
            "documentHighlightProvider",
            "renameProvider",
            "semanticTokensProvider",
            "inlayHintProvider",
            "codeActionProvider",
        )
    )
    assert not capabilities.get("documentFormattingProvider")
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
    identifier = client.send("textDocument/hover", params, request=True)
    client.send("$/cancelRequest", {"id": identifier})
    canceled = client.wait(lambda item: item.get("id") == identifier)
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


@pytest.mark.parametrize("encoding,character", [("utf-8", 26), ("utf-16", 24), ("utf-32", 23)])
def test_negotiated_positions_drive_incremental_edits(encoding, character):
    connection = Client([encoding])
    uri = "untitled:Unicode"
    try:
        assert connection.initialized["capabilities"]["positionEncoding"] == encoding
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
        connection.finish()
    finally:
        if connection.process.poll() is None:
            connection.process.terminate()
            connection.process.wait(timeout=10)


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
    client.saved.clear()

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


def _published(client, uri):
    return [
        message
        for message in client.saved
        if message.get("method") == "textDocument/publishDiagnostics"
        and message["params"]["uri"] == uri
    ]


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
