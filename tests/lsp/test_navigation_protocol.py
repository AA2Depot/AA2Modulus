"""Framed stdio sessions for import path links and authored workspace symbols."""

from __future__ import annotations

import pytest

from tests.support.lsp_client import Client
from tests.support.paths import ROOT

LIBRARY = """macro "say" { param "message" string; WriteLog(message); }
trigger "Welcome" { slot "greeting" string; on CARD_ADDED; let reply: int = 0; }
"""
FIRST = """module "First" {
  global shared: int = 1;
  const Limit: int = 3;
  trigger "Start" { on CARD_ADDED; let counter: int = 0; }
}
"""
SECOND = 'module "Second" { global shared: int = 2; }\n'
_CONTENT_SUPPORT = {"workspace": {"textDocumentContent": {"dynamicRegistration": True}}}


def _position(source: str, offset: int) -> dict[str, int]:
    before = source[:offset]
    return {"line": before.count("\n"), "character": len(before) - (before.rfind("\n") + 1)}


def _range(source: str, needle: str) -> dict[str, dict[str, int]]:
    start = source.index(needle)
    return {"start": _position(source, start), "end": _position(source, start + len(needle))}


def _links(client: Client, uri: str) -> list[dict]:
    return client.request("textDocument/documentLink", {"textDocument": {"uri": uri}})


def _symbols(client: Client, query: str) -> list[tuple[str, str, str | None]]:
    return [
        (item["name"], item["location"]["uri"].rsplit("/", 1)[-1], item.get("containerName"))
        for item in client.request("workspace/symbol", {"query": query})
    ]


def test_import_links_cover_resolved_paths_and_match_definition(tmp_path):
    (tmp_path / "library.aa2mi").write_text(LIBRARY, encoding="utf-8")
    source = (
        'import "library.aa2mi";\nimport "missing.aa2mi";\n'
        'module "M" { trigger "T" { on CARD_ADDED; say("hi"); } }\n'
    )
    client = Client()
    try:
        assert client.initialized["capabilities"]["documentLinkProvider"] == {
            "resolveProvider": False
        }
        uri = (tmp_path / "root.aa2m").as_uri()
        client.open(uri, source)
        (link,) = _links(client, uri)
        assert link == {
            "range": _range(source, '"library.aa2mi"'),
            "target": (tmp_path / "library.aa2mi").as_uri(),
        }
        # F12 on each path agrees with its link: the library resolves, the missing file does not.
        targets = {}
        for needle in ('"library.aa2mi"', '"missing.aa2mi"'):
            point = _position(source, source.index(needle) + 3)
            found = client.request(
                "textDocument/definition", {"textDocument": {"uri": uri}, "position": point}
            )
            targets[needle] = [item["uri"] for item in found]
        assert targets == {'"library.aa2mi"': [link["target"]], '"missing.aa2mi"': []}

        client.open("untitled:Imports", source)
        assert _links(client, "untitled:Imports") == []
        # A syntax error keeps the links of the recovered imports, as F12 does.
        broken = (tmp_path / "broken.aa2m").as_uri()
        client.open(broken, 'import "library.aa2mi";\nmodule "M" { trigger "T" {')
        assert [item["target"] for item in _links(client, broken)] == [link["target"]]
    finally:
        client.finish()


@pytest.mark.parametrize("capabilities", [None, _CONTENT_SUPPORT], ids=["plain", "content"])
def test_workspace_symbols_find_example_templates_and_triggers(capabilities):
    client = Client(
        capabilities=capabilities,
        workspace_folders=[{"uri": (ROOT / "examples").as_uri(), "name": "examples"}],
    )
    try:
        found = client.request("workspace/symbol", {"query": "Init"})
        authored = [item for item in found if item["location"]["uri"].startswith("file:")]
        assert [(item["name"], item.get("containerName")) for item in authored] == [
            ("Init", "Constants Example"),
            ("Init", None),
            ("Initialize", "Library Example"),
        ]
        library = (ROOT / "examples" / "libraries" / "naive.aa2mi").read_text(encoding="utf-8")
        assert authored[1]["location"] == {
            "uri": (ROOT / "examples" / "libraries" / "naive.aa2mi").as_uri(),
            "range": _range(library, '"Init"'),
        }
        assert found[: len(authored)] == authored

        everything = client.request("workspace/symbol", {"query": ""})
        schemes = [item["location"]["uri"].split(":", 1)[0] for item in everything]
        if capabilities is None:
            assert set(schemes) == {"file"}
        else:
            assert len(everything) == 200
            builtins = schemes.index("aa2m-builtin")
            assert set(schemes[:builtins]) == {"file"}
            assert set(schemes[builtins:]) == {"aa2m-builtin"}
    finally:
        client.finish()


def test_workspace_symbols_follow_buffers_and_disk_without_locals(tmp_path):
    (tmp_path / "library.aa2mi").write_text(LIBRARY, encoding="utf-8")
    (tmp_path / "first.aa2m").write_text(FIRST, encoding="utf-8")
    (tmp_path / "second.aa2m").write_text(SECOND, encoding="utf-8")
    client = Client(workspace_folders=[{"uri": tmp_path.as_uri(), "name": "mods"}])
    try:
        assert _symbols(client, "shared") == [
            ("shared", "first.aa2m", "First"),
            ("shared", "second.aa2m", "Second"),
        ]
        assert _symbols(client, "LIMIT") == [("Limit", "first.aa2m", "First")]
        assert _symbols(client, "s") == [
            ("shared", "first.aa2m", "First"),
            ("Start", "first.aa2m", "First"),
            ("say", "library.aa2mi", None),
            ("Second", "second.aa2m", None),
            ("shared", "second.aa2m", "Second"),
            ("First", "first.aa2m", None),
        ]
        for local in ("message", "greeting", "reply", "counter"):
            assert _symbols(client, local) == []

        first = (tmp_path / "first.aa2m").as_uri()
        client.open(first, FIRST)
        client.change(first, FIRST.replace("shared", "opened"), 2)
        (tmp_path / "second.aa2m").write_text(SECOND.replace("shared", "renamed"), encoding="utf-8")
        assert _symbols(client, "shared") == []
        assert _symbols(client, "opened") == [("opened", "first.aa2m", "First")]
        assert _symbols(client, "renamed") == [("renamed", "second.aa2m", "Second")]
    finally:
        client.finish()
