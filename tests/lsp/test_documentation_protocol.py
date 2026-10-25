"""Real stdio authoring: server built-in pages, the built-in list, prose from policy."""

from __future__ import annotations

from aa2modulus.app.editor_catalog.document import editor_catalog
from aa2modulus.app.editor_catalog.pages import page
from aa2modulus.syntax.lexicon import source_lexicon
from tests.support.lsp_client import Client

_CONTENT_SUPPORT = {"workspace": {"textDocumentContent": {"dynamicRegistration": True}}}


def test_stdio_builtin_hover_completion_and_page_definition(context):
    client = Client(snippet_support=True, capabilities=_CONTENT_SUPPORT)
    try:
        capabilities = client.initialized["capabilities"]
        features = capabilities["experimental"]["aa2modulus"]
        assert features["contractVersion"] == 1
        assert features["builtinCatalog"] is True
        assert features["syntax"]["fingerprint"] == source_lexicon().fingerprint
        assert capabilities["workspace"]["textDocumentContent"] == {"schemes": ["aa2m-builtin"]}
        description = context.metadata.action(108).description
        uri = "untitled:Builtins"
        source = 'module "M" { trigger "T" { Notification("hello"); Noti'
        client.open(uri, source)
        point = {"line": 0, "character": source.index("Notification") + 3}
        params = {"textDocument": {"uri": uri}, "position": point}
        hover = client.request("textDocument/hover", params)
        assert description in hover["contents"]["value"]
        assert (
            "Notification(text: string, isImportant: bool = false)" in (hover["contents"]["value"])
        )
        (target,) = client.request("textDocument/definition", params)
        assert target["uri"] == "aa2m-builtin:/action-108.md"
        assert target["range"]["start"] == {"line": 0, "character": 0}

        completion_params = {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": len(source)},
        }
        items = client.request("textDocument/completion", completion_params)
        item = next(item for item in items if item["label"] == "Notification")
        assert item["insertTextFormat"] == 2
        assert item["textEdit"]["newText"] == 'Notification(${1:""});$0'
        assert description in item["documentation"]["value"]
        assert "command" not in item  # Parameter hints belong to the editor adapter.
        client.finish()
    finally:
        if client.process.poll() is None:
            client.process.terminate()
            client.process.wait(timeout=10)


def test_stdio_serves_builtin_pages_and_ranked_builtin_symbols():
    document, _ = editor_catalog()
    notification = next(item for item in document["entries"] if item["id"] == "action-108")
    client = Client(capabilities=_CONTENT_SUPPORT)
    try:
        content = client.request(
            "workspace/textDocumentContent", {"uri": "aa2m-builtin:/action-108.md"}
        )
        assert content == {"text": page(notification, website=None)}
        unknown = client.request("workspace/textDocumentContent", {"uri": "aa2m-builtin:/nope.md"})
        assert unknown["text"].startswith("# Unknown built-in\n")

        symbols = client.request("workspace/symbol", {"query": "notification"})
        assert symbols[0] == {
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
        everything = client.request("workspace/symbol", {"query": ""})
        assert len(everything) == 200
        assert all(item["location"]["uri"].startswith("aa2m-builtin:/") for item in everything)
        client.finish()
    finally:
        if client.process.poll() is None:
            client.process.terminate()
            client.process.wait(timeout=10)


def test_stdio_without_content_support_has_no_builtin_targets(client):
    uri = "untitled:Builtins"
    source = 'module "M" { trigger "T" { Notification("hello"); } }'
    client.open(uri, source)
    point = {"line": 0, "character": source.index("Notification")}
    params = {"textDocument": {"uri": uri}, "position": point}
    assert client.request("textDocument/definition", params) == []
    assert client.request("workspace/symbol", {"query": "notification"}) == []
