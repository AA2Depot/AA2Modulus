"""Built-in pages and symbols over stdio: offered only to a client that supports them."""

from __future__ import annotations

import re

from aa2modulus.app.editor_manifest import editor_manifest


def test_initialize_offers_every_feature_the_client_supports(full_client, context):
    capabilities = full_client.initialized["capabilities"]
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
            "builtinCatalog": True,
            "completionSnippets": True,
        }
    }
    assert capabilities["workspace"]["textDocumentContent"] == {"schemes": ["aa2m-builtin"]}


def test_release_manifest_agrees_with_what_a_fully_capable_client_receives(full_client):
    manifest = editor_manifest()
    initialized = full_client.initialized

    assert initialized["serverInfo"]["version"] == manifest["version"]
    assert initialized["capabilities"]["experimental"]["aa2modulus"] == {
        "contractVersion": manifest["contractVersion"],
        "syntax": manifest["syntax"],
        **manifest["features"],
    }


def test_builtin_definition_points_at_a_page_the_server_serves(full_client):
    uri = "untitled:Builtins"
    source = 'module "M" { trigger "T" { Notification("hello"); } }'
    full_client.open(uri, source)
    point = {"line": 0, "character": source.index("Notification") + 3}

    (target,) = full_client.request(
        "textDocument/definition", {"textDocument": {"uri": uri}, "position": point}
    )
    assert target["uri"] == "aa2m-builtin:/action-108.md"
    assert target["range"]["start"] == {"line": 0, "character": 0}

    content = full_client.request("workspace/textDocumentContent", {"uri": target["uri"]})
    assert content["text"].startswith(
        "# Notification\n\n```aa2m\nNotification(text: string, isImportant: bool = false)\n```\n"
    )
    assert content["text"].endswith("Native name: Notification (General). ID: `action-108`\n")
    unknown = full_client.request("workspace/textDocumentContent", {"uri": "aa2m-builtin:/nope.md"})
    assert unknown["text"].startswith("# Unknown built-in\n")


def test_builtin_symbols_are_ranked_by_name_and_located_at_their_page(full_client):
    symbols = full_client.request("workspace/symbol", {"query": "notification"})
    builtins = [item for item in symbols if item["location"]["uri"].startswith("aa2m-builtin:")]

    assert builtins[0] == {
        "name": "Notification",
        "kind": 12,
        "containerName": "Notification",
        "location": {
            "uri": "aa2m-builtin:/action-108.md",
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 0},
            },
        },
    }


def test_without_content_support_there_are_no_builtin_targets(client):
    uri = "untitled:BuiltinsPlain"
    source = 'module "M" { trigger "T" { Notification("hello"); } }'
    client.open(uri, source)
    point = {"line": 0, "character": source.index("Notification")}

    assert (
        client.request("textDocument/definition", {"textDocument": {"uri": uri}, "position": point})
        == []
    )
    for query in ("notification", ""):
        symbols = client.request("workspace/symbol", {"query": query})
        assert not [item for item in symbols if item["location"]["uri"].startswith("aa2m-builtin:")]
