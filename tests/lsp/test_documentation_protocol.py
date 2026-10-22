"""Real stdio authoring: built-in pages under a client base URI, prose from policy."""

from __future__ import annotations

from tests.support.lsp_client import Client


def test_stdio_builtin_hover_completion_and_page_definition(context):
    client = Client(
        initialization_options={"builtinDocumentationBaseUri": "aa2m-builtin:/"},
        snippet_support=True,
    )
    try:
        assert client.initialized["capabilities"]["experimental"] == {
            "aa2modulus": {
                "builtinDocumentationBaseUri": True,
                "catalogFingerprint": context.catalog.fingerprint,
            }
        }
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
