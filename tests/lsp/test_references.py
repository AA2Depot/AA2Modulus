"""References, document highlights and rebinding-validated rename."""

from __future__ import annotations

from pathlib import Path

import pytest
from lsprotocol import types

from aa2modulus.app.compile import compile_source
from aa2modulus.lsp.features.references import document_highlights, reference_locations, target_at
from aa2modulus.lsp.features.rename import RenameError, StaleRename, prepare_rename, rename
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.workspace.documents import SourceWorkspace
from aa2modulus.lsp.workspace.index import WorkspaceIndex, analyze_closed, discover
from tests.support.lsp_workspace import analyze_workspace

LOCALS = """module "M" {
  global g: int = 1;
  trigger "T" {
    on CARD_ADDED;
    let count: int = 0;
    count = count + 1;
    variable("count") = 2;
    for count from 0 to 3 { WriteLog("count"); }
    // count in a comment
    if (count > 1) { WriteLog("big"); }
  }
}"""

LIBRARY = """macro say { param message string; WriteLog(message); }
const Greeting: string = "hello";
trigger "Welcome" { slot greeting string; on CARD_ADDED; WriteLog(greeting); }
"""

ROOT = """import "library.aa2mi";
module "M" {
  import.trigger "Welcome" { slot greeting = Greeting; }
  trigger "T" { on CARD_ADDED; say(Greeting); Say("again"); }
}"""


def _open(source: str, context, uri: str = "untitled:A"):
    workspace = SourceWorkspace()
    workspace.open(uri, source, 1)
    return workspace, analyze_workspace(workspace, uri, context)


def _at(source: str, needle: str, offset: int = 0, *, start: int = 0) -> types.Position:
    return PositionCodec(source).position(source.index(needle, start) + offset)


def _library_workspace(tmp_path, context):
    library = tmp_path / "library.aa2mi"
    root = tmp_path / "root.aa2m"
    library.write_text(LIBRARY, encoding="utf-8")
    root.write_text(ROOT, encoding="utf-8")
    workspace = SourceWorkspace()
    workspace.open(root.as_uri(), ROOT, 1)
    workspace.open(library.as_uri(), LIBRARY, 1, "aa2mi")
    snapshots = [
        analyze_workspace(workspace, root.as_uri(), context),
        analyze_workspace(workspace, library.as_uri(), context),
    ]
    return workspace, snapshots, root, library


def test_highlights_mark_declarations_and_assignment_targets_as_writes(context):
    _, snapshot = _open(LOCALS, context)
    highlights = document_highlights(snapshot, _at(LOCALS, "count = count"), "utf-16")
    codec = PositionCodec(LOCALS)
    marked = {
        (LOCALS[codec.offset(item.range.start) : codec.offset(item.range.end)], item.kind)
        for item in highlights
    }
    write, read = types.DocumentHighlightKind.Write, types.DocumentHighlightKind.Read
    assert len(highlights) == 6
    assert marked == {("count", write), ("count", read), ('"count"', write)}
    # The string literal and the comment are not occurrences.
    assert all(LOCALS[codec.offset(item.range.start) - 1] != "/" for item in highlights)
    assert document_highlights(snapshot, _at(LOCALS, "CARD_ADDED"), "utf-16") == []


def test_references_cover_library_uses_from_every_analysis(tmp_path, context):
    workspace, snapshots, root, library = _library_workspace(tmp_path, context)
    root_snapshot = snapshots[0]
    target = target_at(root_snapshot, _at(ROOT, "say("), "utf-16")
    assert target is not None and target.name == "say"
    locations = reference_locations(
        snapshots, target, "utf-16", workspace.uri_for, include_declaration=True
    )
    assert [(item.uri, item.range.start.line) for item in locations] == [
        (library.as_uri(), 0),
        (root.as_uri(), 3),
        (root.as_uri(), 3),
    ]
    without = reference_locations(
        snapshots, target, "utf-16", workspace.uri_for, include_declaration=False
    )
    assert [item.uri for item in without] == [root.as_uri(), root.as_uri()]


def test_prepare_rename_refuses_built_ins_and_offers_the_declared_name(context):
    _, snapshot = _open(LOCALS, context)
    with pytest.raises(RenameError, match="built-in"):
        prepare_rename(snapshot, _at(LOCALS, "WriteLog"), "utf-16")
    placeholder = prepare_rename(snapshot, _at(LOCALS, '"count")', 2), "utf-16")
    assert placeholder is not None and placeholder.placeholder == "count"
    assert prepare_rename(snapshot, _at(LOCALS, "module"), "utf-16") is None


def test_rename_local_edits_every_use_form_and_nothing_in_strings_or_comments(context):
    _, snapshot = _open(LOCALS, context)
    target = target_at(snapshot, _at(LOCALS, "count: int"), "utf-16")
    plan = rename([snapshot], target, "total", context)
    assert plan.files["untitled:A"].edited == LOCALS.replace("let count", "let total").replace(
        "count = count", "total = total"
    ).replace('variable("count")', 'variable("total")').replace("for count", "for total").replace(
        "(count > 1)", "(total > 1)"
    )


def test_rename_to_a_non_identifier_quotes_declarations_and_wraps_uses(context):
    _, snapshot = _open(LOCALS, context)
    target = target_at(snapshot, _at(LOCALS, "count: int"), "utf-16")
    edited = rename([snapshot], target, "my count", context).files["untitled:A"].edited
    assert 'let "my count": int = 0;' in edited
    assert 'variable("my count") = variable("my count") + 1;' in edited
    assert 'for "my count" from 0 to 3 { WriteLog("count"); }' in edited
    assert 'if (variable("my count") > 1)' in edited


def test_rename_to_a_reserved_word_quotes_declarations_and_wraps_uses(context):
    _, snapshot = _open(LOCALS, context)
    target = target_at(snapshot, _at(LOCALS, "count: int"), "utf-16")
    edited = rename([snapshot], target, "If", context).files["untitled:A"].edited
    assert 'let "If": int = 0;' in edited
    assert 'variable("If") = variable("If") + 1;' in edited
    assert 'for "If" from 0 to 3' in edited


def test_rename_refuses_shadowing_protected_names_and_new_errors(context):
    _, snapshot = _open(LOCALS, context)
    target = target_at(snapshot, _at(LOCALS, "count: int"), "utf-16")
    with pytest.raises(RenameError, match="refer to the global 'g'"):
        rename([snapshot], target, "g", context)
    with pytest.raises(RenameError, match="protected"):
        rename([snapshot], target, "ThisCard", context)
    with pytest.raises(RenameError, match="cannot be empty"):
        rename([snapshot], target, "", context)
    duplicate = LOCALS.replace(
        "let count: int = 0;", "let count: int = 0;\n    let other: int = 0;"
    )
    _, snapshot = _open(duplicate, context)
    target = target_at(snapshot, _at(duplicate, "count: int"), "utf-16")
    with pytest.raises(RenameError, match="would cause an error"):
        rename([snapshot], target, "other", context)


def test_unchanged_name_produces_no_edits(context):
    _, snapshot = _open(LOCALS, context)
    target = target_at(snapshot, _at(LOCALS, "count: int"), "utf-16")
    assert rename([snapshot], target, "count", context).files == {}


def _compile(tmp_path, texts: dict[str, str]) -> bytes:
    for name, text in texts.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return compile_source(
        texts["root.aa2m"], filename=str(tmp_path / "root.aa2m"), import_base=tmp_path
    )


@pytest.mark.parametrize(
    ("needle", "offset", "new_name"),
    [
        ("say(", 0, "announce"),
        ("Greeting)", 0, "Salutation"),
        ("slot greeting =", 5, "salutation"),
        ("message string", 0, "text"),
    ],
)
def test_library_renames_compile_byte_identically(tmp_path, context, needle, offset, new_name):
    before = _compile(tmp_path, {"library.aa2mi": LIBRARY, "root.aa2m": ROOT})
    _, snapshots, root, library = _library_workspace(tmp_path, context)
    source, snapshot = (ROOT, snapshots[0]) if needle in ROOT else (LIBRARY, snapshots[1])
    target = target_at(snapshot, _at(source, needle, offset), "utf-16")
    plan = rename(snapshots, target, new_name, context)
    texts = {
        path.name: plan.files[str(path)].edited if str(path) in plan.files else text
        for path, text in ((library, LIBRARY), (root, ROOT))
    }
    assert new_name in texts["library.aa2mi"]
    assert _compile(tmp_path, texts) == before


def test_slot_rename_from_an_instantiation_site_renames_the_template_slot(tmp_path, context):
    _, snapshots, root, library = _library_workspace(tmp_path, context)
    target = target_at(snapshots[0], _at(ROOT, "slot greeting", 5), "utf-16")
    assert target is not None and target.span.filename == str(library)
    plan = rename(snapshots, target, "salutation", context)
    assert "slot salutation string; on CARD_ADDED; WriteLog(salutation);" in (
        plan.files[str(library)].edited
    )
    assert "slot salutation = Greeting;" in plan.files[str(root)].edited


def test_slot_binding_names_resolve_while_the_module_has_errors(tmp_path, context):
    broken = ROOT.replace('Say("again");', 'Say("again"); Missing();')
    (tmp_path / "library.aa2mi").write_text(LIBRARY, encoding="utf-8")
    workspace = SourceWorkspace()
    root = tmp_path / "root.aa2m"
    workspace.open(root.as_uri(), broken, 1)
    snapshot = analyze_workspace(workspace, root.as_uri(), context)
    assert snapshot.analysis.failure is not None
    target = target_at(snapshot, _at(broken, "slot greeting", 5), "utf-16")
    assert target is not None and target.name == "greeting"
    assert target.span.filename == str(tmp_path / "library.aa2mi")


def test_template_rename_keeps_the_instantiated_trigger_name(tmp_path, context):
    before = _compile(tmp_path, {"library.aa2mi": LIBRARY, "root.aa2m": ROOT})
    _, snapshots, root, library = _library_workspace(tmp_path, context)
    target = target_at(snapshots[1], _at(LIBRARY, '"Welcome"', 1), "utf-16")
    plan = rename(snapshots, target, "Greeter", context)
    assert 'trigger "Greeter" {' in plan.files[str(library)].edited
    root_text = plan.files[str(root)].edited
    assert 'import.trigger "Greeter" "Welcome" {' in root_text
    texts = {"library.aa2mi": plan.files[str(library)].edited, "root.aa2m": root_text}
    assert _compile(tmp_path, texts) == before


def test_constant_rename_to_a_non_identifier_uses_const_references(tmp_path, context):
    _, snapshots, root, library = _library_workspace(tmp_path, context)
    target = target_at(snapshots[1], _at(LIBRARY, "Greeting:"), "utf-16")
    plan = rename(snapshots, target, "Warm Greeting", context)
    assert 'const "Warm Greeting": string = "hello";' in plan.files[str(library)].edited
    assert 'say(const("Warm Greeting"));' in plan.files[str(root)].edited


def test_macro_rename_requires_an_identifier_and_rewrites_any_case(tmp_path, context):
    _, snapshots, root, _ = _library_workspace(tmp_path, context)
    target = target_at(snapshots[0], _at(ROOT, "Say("), "utf-16")
    with pytest.raises(RenameError, match="identifiers"):
        rename(snapshots, target, "two words", context)
    edited = rename(snapshots, target, "announce", context).files[str(root)].edited
    assert 'announce(Greeting); announce("again");' in edited


def test_disagreeing_analyses_are_stale(tmp_path, context):
    workspace, snapshots, _, library = _library_workspace(tmp_path, context)
    target = target_at(snapshots[0], _at(ROOT, "say("), "utf-16")
    workspace.change(library.as_uri(), LIBRARY + "\n", 2)
    changed = analyze_workspace(workspace, library.as_uri(), context)
    with pytest.raises(StaleRename):
        rename([snapshots[0], changed], target, "announce", context)


def test_discovery_skips_hidden_entries_and_reports_the_cap(tmp_path):
    (tmp_path / "a.aa2m").write_text("", encoding="utf-8")
    (tmp_path / "b.aa2mi").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "c.aa2m").write_text("", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "d.aa2m").write_text("", encoding="utf-8")

    files, truncated = discover((str(tmp_path),))
    assert [Path(item).name for item in files] == ["a.aa2m", "b.aa2mi", "d.aa2m"]
    assert not truncated
    assert discover((str(tmp_path),), cap=3) == (files, False)
    assert discover((str(tmp_path),), cap=2) == (files[:2], True)


def test_index_reuses_analyses_until_an_input_changes(tmp_path, context):
    library = tmp_path / "library.aa2mi"
    root = tmp_path / "root.aa2m"
    library.write_text(LIBRARY, encoding="utf-8")
    root.write_text(ROOT, encoding="utf-8")
    index = WorkspaceIndex()
    snapshot, signature = analyze_closed(str(root), context, {})
    index.store(str(root), snapshot, signature)
    assert index.cached(str(root), {}) is snapshot
    # An open buffer for an import replaces the disk text.
    assert index.cached(str(root), {str(library): LIBRARY}) is None
    library.write_text(LIBRARY + "\n", encoding="utf-8")
    assert index.cached(str(root), {}) is None
    index.changed([types.FileEvent(root.as_uri(), types.FileChangeType.Changed)])
    assert str(root) not in index.entries
