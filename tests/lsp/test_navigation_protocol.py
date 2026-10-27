"""Framed stdio sessions for import path links and authored workspace symbols."""

from __future__ import annotations

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


def _position(source: str, offset: int) -> dict[str, int]:
    before = source[:offset]
    return {"line": before.count("\n"), "character": len(before) - (before.rfind("\n") + 1)}


def _range(source: str, needle: str) -> dict[str, dict[str, int]]:
    start = source.index(needle)
    return {"start": _position(source, start), "end": _position(source, start + len(needle))}


def _links(client: Client, uri: str) -> list[dict]:
    return client.request("textDocument/documentLink", {"textDocument": {"uri": uri}})


def _symbols(client: Client, query: str, folder) -> list[tuple[str, str, str | None]]:
    """The ``(name, file, container)`` of every result located in ``folder``."""

    return [
        (item["name"], item["location"]["uri"].rsplit("/", 1)[-1], item.get("containerName"))
        for item in client.request("workspace/symbol", {"query": query})
        if item["location"]["uri"].startswith(folder.as_uri())
    ]


def test_import_links_cover_resolved_paths_and_match_definition(client, tmp_path):
    (tmp_path / "library.aa2mi").write_text(LIBRARY, encoding="utf-8")
    source = (
        'import "library.aa2mi";\nimport "missing.aa2mi";\n'
        'module "M" { trigger "T" { on CARD_ADDED; say("hi"); } }\n'
    )
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

    client.open("untitled:ImportLinks", source)
    assert _links(client, "untitled:ImportLinks") == []
    # A syntax error keeps the links of the recovered imports, as F12 does.
    broken = (tmp_path / "broken.aa2m").as_uri()
    client.open(broken, 'import "library.aa2mi";\nmodule "M" { trigger "T" {')
    assert [item["target"] for item in _links(client, broken)] == [link["target"]]


def test_workspace_symbols_find_example_templates_and_triggers_before_builtins(full_client):
    examples = ROOT / "examples"
    with full_client.folder(examples, "examples"):
        found = full_client.request("workspace/symbol", {"query": "Init"})
        everything = full_client.request("workspace/symbol", {"query": ""})

    authored = [item for item in found if item["location"]["uri"].startswith(examples.as_uri())]
    assert [(item["name"], item.get("containerName")) for item in authored] == [
        ("Init", "Constants Example"),
        ("Init", None),
        ("Initialize", "Library Example"),
    ]
    library = (examples / "libraries" / "naive.aa2mi").read_text(encoding="utf-8")
    assert authored[1]["location"] == {
        "uri": (examples / "libraries" / "naive.aa2mi").as_uri(),
        "range": _range(library, '"Init"'),
    }

    # The list holds at most 200 results: authored ones first, then built-ins.
    schemes = [item["location"]["uri"].split(":", 1)[0] for item in everything]
    first_builtin = schemes.index("aa2m-builtin")
    assert len(everything) == 200
    assert "file" in schemes[:first_builtin]
    assert set(schemes[first_builtin:]) == {"aa2m-builtin"}


def test_workspace_symbols_follow_buffers_and_disk_without_locals(client, tmp_path):
    (tmp_path / "library.aa2mi").write_text(LIBRARY, encoding="utf-8")
    (tmp_path / "first.aa2m").write_text(FIRST, encoding="utf-8")
    (tmp_path / "second.aa2m").write_text(SECOND, encoding="utf-8")
    with client.folder(tmp_path, "mods"):
        assert _symbols(client, "shared", tmp_path) == [
            ("shared", "first.aa2m", "First"),
            ("shared", "second.aa2m", "Second"),
        ]
        assert _symbols(client, "LIMIT", tmp_path) == [("Limit", "first.aa2m", "First")]
        assert _symbols(client, "s", tmp_path) == [
            ("shared", "first.aa2m", "First"),
            ("Start", "first.aa2m", "First"),
            ("say", "library.aa2mi", None),
            ("Second", "second.aa2m", None),
            ("shared", "second.aa2m", "Second"),
            ("First", "first.aa2m", None),
        ]
        for local in ("message", "greeting", "reply", "counter"):
            assert _symbols(client, local, tmp_path) == []

        first = (tmp_path / "first.aa2m").as_uri()
        client.open(first, FIRST)
        client.change(first, FIRST.replace("shared", "opened"), 2)
        (tmp_path / "second.aa2m").write_text(SECOND.replace("shared", "renamed"), encoding="utf-8")
        assert _symbols(client, "shared", tmp_path) == []
        assert _symbols(client, "opened", tmp_path) == [("opened", "first.aa2m", "First")]
        assert _symbols(client, "renamed", tmp_path) == [("renamed", "second.aa2m", "Second")]
