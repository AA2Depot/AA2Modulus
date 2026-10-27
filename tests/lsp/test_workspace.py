"""Unsaved imports, dependency ownership, and superseded editor snapshots."""

from __future__ import annotations

from lsprotocol import types

from aa2modulus.context.operation import SourceContext
from aa2modulus.lsp.features.navigation import definition, document_symbols, hover
from aa2modulus.lsp.protocol.diagnostics import aggregate_diagnostics
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.workspace.documents import SourceWorkspace
from tests.support.lsp_workspace import analyze_workspace, notification_text


def test_unsaved_transitive_libraries_override_disk_and_close_returns_to_disk(tmp_path, context):
    root = tmp_path / "root.aa2m"
    outer = tmp_path / "outer.aa2mi"
    leaf = tmp_path / "leaf.aa2mi"
    outer.write_text('import "leaf.aa2mi";', encoding="utf-8")
    leaf.write_text('macro emit { Notification("disk"); }', encoding="utf-8")
    workspace = SourceWorkspace()
    source = 'import "outer.aa2mi"; module "M" { trigger "T" { emit(); } }'
    workspace.open(root.as_uri(), source, 1)
    workspace.open(leaf.as_uri(), 'macro emit { Notification("buffer"); }', 1, "aa2mi")
    snapshot = analyze_workspace(workspace, root.as_uri(), context)

    assert notification_text(snapshot) == "buffer"
    workspace.close(leaf.as_uri())
    snapshot = analyze_workspace(workspace, root.as_uri(), context)
    assert notification_text(snapshot) == "disk"


def test_failed_edges_survive_syntax_failure_and_missing_library_creation(tmp_path, context):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "missing.aa2mi"
    workspace = SourceWorkspace()
    source = 'import "missing.aa2mi"; module "M" {}'
    workspace.open(root.as_uri(), source, 1)
    snapshot = analyze_workspace(workspace, root.as_uri(), context)
    assert snapshot.analysis.result.errors[0].code == "IMPORT_READ_ERROR"
    workspace.change(root.as_uri(), "module", 2)
    analyze_workspace(workspace, root.as_uri(), context)
    library.write_text("macro emit {}", encoding="utf-8")
    assert workspace.poll_disk() == {root.as_uri()}

    workspace.change(root.as_uri(), 'module "M" {}', 3)
    analyze_workspace(workspace, root.as_uri(), context)
    assert workspace.poll_disk() == set()


def test_snapshots_reject_overlay_and_disk_changes_without_reusing_navigation(tmp_path, context):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    library.write_text("macro emit {}", encoding="utf-8")
    workspace = SourceWorkspace()
    source = 'import "lib.aa2mi"; module "M" { trigger "T" { emit(); } }'
    workspace.open(root.as_uri(), source, 1)
    revision = workspace.revision
    snapshot = analyze_workspace(workspace, root.as_uri(), context)
    library.write_text('macro emit { Notification("changed"); }', encoding="utf-8")
    assert not workspace.accept(snapshot, revision)

    snapshot = analyze_workspace(workspace, root.as_uri(), context)
    position = PositionCodec(source).position(source.index("emit()"))
    assert definition(snapshot, position, "utf-16", workspace)
    workspace.change(root.as_uri(), 'module "M" { @ }', 2)
    assert not workspace.accept(snapshot, revision)
    assert root.as_uri() not in workspace.snapshots
    broken = analyze_workspace(workspace, root.as_uri(), context)
    assert definition(broken, position, "utf-16", workspace) == []
    assert hover(broken, position, "utf-16") is None


def test_shared_import_errors_deduplicate_and_preserve_each_owner_note(tmp_path, context):
    library = tmp_path / "lib.aa2mi"
    library.write_text("macro emit { Missing(); }", encoding="utf-8")
    workspace = SourceWorkspace()
    for name in ("one", "two"):
        path = tmp_path / f"{name}.aa2m"
        workspace.open(path.as_uri(), 'import "lib.aa2mi"; module "M" {}', 1)
    for uri in workspace.documents:
        analyze_workspace(workspace, uri, context)
    diagnostics = aggregate_diagnostics(workspace.snapshots.values(), workspace, "utf-16")
    (error,) = diagnostics[library.as_uri()]
    assert error.code == "UNKNOWN_ACTION_NAME"
    assert {item.location.uri for item in error.related_information} == {
        (tmp_path / "one.aa2m").as_uri(),
        (tmp_path / "two.aa2m").as_uri(),
    }
    assert all(note.location.range.end.character == 19 for note in error.related_information)
    workspace.close((tmp_path / "one.aa2m").as_uri())
    assert library.as_uri() in aggregate_diagnostics(
        workspace.snapshots.values(), workspace, "utf-16"
    )
    workspace.close((tmp_path / "two.aa2m").as_uri())
    assert aggregate_diagnostics(workspace.snapshots.values(), workspace, "utf-16") == {}


def test_navigation_hover_and_symbols_use_authored_tokens_and_client_uri_aliases(tmp_path, context):
    root = tmp_path / "root name.aa2m"
    library = tmp_path / "lib name.aa2mi"
    library_source = 'macro emit { param value int; Notification("x"); }'
    library.write_text(library_source, encoding="utf-8")
    alias = library.as_uri().replace("file:///", "file://localhost/", 1)
    source = (
        'import "lib name.aa2mi"; module "😀" { global x: int = 1; trigger "T" {\r\n'
        '  let x: string = "shadow"; emit(x); Notification("x");\r\n'
        "} }"
    )
    workspace = SourceWorkspace()
    workspace.open(root.as_uri(), source, 1)
    workspace.open(alias, library_source, 4, "aa2mi")
    snapshot = analyze_workspace(workspace, root.as_uri(), context)
    codec = PositionCodec(source)
    macro = definition(snapshot, codec.position(source.index("emit(x)")), "utf-16", workspace)
    assert macro[0].uri == alias
    assert macro[0].range == types.Range(types.Position(0, 6), types.Position(0, 10))
    variable = definition(snapshot, codec.position(source.index("x);")), "utf-16", workspace)
    assert variable[0].uri == root.as_uri()
    assert variable[0].range == codec.range(snapshot.analysis.ast.module.globals[0].name_span)
    info = hover(snapshot, codec.position(source.index('Notification("x")')), "utf-16")
    assert "Notification(text: string, isImportant: bool = false)" in info.contents.value
    assert (
        definition(snapshot, codec.position(source.index('Notification("x")')), "utf-16", workspace)
        == []
    )
    symbols = document_symbols(snapshot, "utf-16")
    assert [item.name for item in symbols] == ["😀"]
    assert [item.name for item in symbols[0].children] == ["x", "T"]
    assert [item.name for item in symbols[0].children[1].children] == ["x"]


def test_untitled_documents_analyze_locally_and_do_not_read_imports(context):
    workspace = SourceWorkspace()
    workspace.open("untitled:Example", 'module "M" {}', 1)
    assert analyze_workspace(workspace, "untitled:Example", context).analysis.result.is_valid
    workspace.change("untitled:Example", 'import "lib.aa2mi"; module "M" {}', 2)
    snapshot = analyze_workspace(workspace, "untitled:Example", context)
    assert snapshot.analysis.result.errors[0].code == "IMPORT_RESOLVER_REQUIRED"


def test_reanalysis_of_one_owner_does_not_hide_disk_changes_from_other_owners(tmp_path, context):
    library = tmp_path / "lib.aa2mi"
    library.write_text("macro emit {}", encoding="utf-8")
    workspace = SourceWorkspace()
    roots = [(tmp_path / f"{name}.aa2m").as_uri() for name in ("one", "two")]
    for uri in roots:
        workspace.open(uri, 'import "lib.aa2mi"; module "M" {}', 1)
    for uri in roots:
        analyze_workspace(workspace, uri, context)
    library.write_text('macro emit { Notification("changed"); }', encoding="utf-8")
    analyze_workspace(workspace, roots[0], context)
    assert workspace.poll_disk() == set(roots)


def test_definition_finds_later_locals_by_binder_scope_and_type(context):
    source = """module "M" {
  global choice: string = "global";
  trigger "First" {
    on CARD_ADDED;
    let ahead: int = later;
    let later: int = 3;
    let count: int = 7;
    let selected: int = count;
  }
  trigger "Second" {
    on CARD_ADDED;
    let selected: string = choice;
  }
}"""
    workspace = SourceWorkspace()
    uri = "untitled:Scopes"
    workspace.open(uri, source, 1)
    snapshot = analyze_workspace(workspace, uri, context)
    codec = PositionCodec(source)

    (later_target,) = definition(
        snapshot, codec.position(source.index("later;")), "utf-16", workspace
    )
    assert later_target.uri == uri
    assert later_target.range.start == codec.position(source.index("later: int"))

    local_use = source.index("count;", source.index("let selected: int"))
    (local_target,) = definition(snapshot, codec.position(local_use), "utf-16", workspace)
    assert local_target.uri == uri
    assert local_target.range.start == codec.position(source.index("count: int"))

    second_choice = source.rindex("choice;")
    (global_target,) = definition(snapshot, codec.position(second_choice), "utf-16", workspace)
    assert global_target.uri == uri
    assert global_target.range.start == codec.position(source.index("choice: string"))


def test_definition_targets_import_path_macro_parameter_and_template_slot(tmp_path, context):
    library = tmp_path / "library.aa2mi"
    root = tmp_path / "root.aa2m"
    library_source = """macro "say" { param "message" string; WriteLog(message); }
trigger "Welcome" { slot "greeting" string; on CARD_ADDED; WriteLog(greeting); }"""
    library.write_text(library_source, encoding="utf-8")
    context = SourceContext.create(filename=str(root))
    source = """import "library.aa2mi";
module "M" {
  global greeting: string = "hello";
  import.trigger "Welcome" "Imported" { slot "greeting" = greeting; }
  trigger "T" { on CARD_ADDED; say("hello"); }
}"""
    workspace = SourceWorkspace()
    workspace.open(root.as_uri(), source, 1)
    workspace.open(library.as_uri(), library_source, 1, "aa2mi")
    snapshot = analyze_workspace(workspace, root.as_uri(), context)
    root_codec = PositionCodec(source)
    library_codec = PositionCodec(library_source)

    (import_target,) = definition(
        snapshot, root_codec.position(source.index("library.aa2mi") + 3), "utf-16", workspace
    )
    assert import_target.uri == library.as_uri()
    assert import_target.range == types.Range(types.Position(0, 0), types.Position(0, 0))

    library_snapshot = analyze_workspace(workspace, library.as_uri(), context)
    macro_use = library_source.index("WriteLog(message)") + len("WriteLog(")
    (parameter_target,) = definition(
        library_snapshot, library_codec.position(macro_use), "utf-16", workspace
    )
    assert parameter_target.uri == library.as_uri()
    assert parameter_target.range.start == library_codec.position(library_source.index('"message"'))

    slot_use = library_source.rindex("greeting")
    (slot_target,) = definition(
        library_snapshot, library_codec.position(slot_use), "utf-16", workspace
    )
    assert slot_target.uri == library.as_uri()
    assert slot_target.range.start == library_codec.position(library_source.index('"greeting"'))


def test_published_diagnostics_append_help_to_the_message(tmp_path, context):
    root = tmp_path / "root.aa2m"
    workspace = SourceWorkspace()
    workspace.open(
        root.as_uri(), 'module "M" { trigger "T" { Character.SetIntelligenceValue(1); } }', 1
    )
    analyze_workspace(workspace, root.as_uri(), context)

    (error,) = aggregate_diagnostics(workspace.snapshots.values(), workspace, "utf-16")[
        root.as_uri()
    ]
    assert error.code == "UNKNOWN_ACTION_NAME"
    headline, help_line = error.message.split("\n")
    assert "Character.SetIntelligenceValue" in headline
    assert help_line == "help: use '<card>.SetIntelligenceValue(...)'"


def test_out_of_range_int_literal_is_a_live_diagnostic(tmp_path, context):
    root = tmp_path / "root.aa2m"
    workspace = SourceWorkspace()
    workspace.open(root.as_uri(), 'module "M" {\n  global big: int = 9999999999999;\n}\n', 1)
    analyze_workspace(workspace, root.as_uri(), context)

    (error,) = aggregate_diagnostics(workspace.snapshots.values(), workspace, "utf-16")[
        root.as_uri()
    ]
    assert error.code == "INT_OUT_OF_RANGE"
    assert error.range == types.Range(types.Position(1, 20), types.Position(1, 33))


def _codes(workspace: SourceWorkspace, uri: str) -> list[str]:
    published = aggregate_diagnostics(workspace.snapshots.values(), workspace, "utf-16")
    return [str(item.code) for item in published.get(uri, [])]


BROKEN = 'module "M" { global big: int = 9999999999999; }'
FIXED = 'module "M" { global big: int = 1; }'


def test_closed_saved_file_keeps_its_diagnostics_without_reanalysis(tmp_path, context):
    path = tmp_path / "broken.aa2m"
    path.write_text(BROKEN, encoding="utf-8")
    workspace = SourceWorkspace()
    workspace.open(path.as_uri(), BROKEN, 1)
    analyze_workspace(workspace, path.as_uri(), context)

    assert workspace.close(path.as_uri()) == set()
    assert path.as_uri() not in workspace.documents
    assert _codes(workspace, path.as_uri()) == ["INT_OUT_OF_RANGE"]


def test_closed_file_with_discarded_edits_is_rechecked_from_disk(tmp_path, context):
    path = tmp_path / "broken.aa2m"
    path.write_text(BROKEN, encoding="utf-8")
    workspace = SourceWorkspace()
    workspace.open(path.as_uri(), FIXED, 1)
    analyze_workspace(workspace, path.as_uri(), context)
    assert _codes(workspace, path.as_uri()) == []

    assert workspace.close(path.as_uri()) == {path.as_uri()}
    analyze_workspace(workspace, path.as_uri(), context)
    assert _codes(workspace, path.as_uri()) == ["INT_OUT_OF_RANGE"]


def test_retained_file_follows_disk_changes_and_deletion(tmp_path, context):
    path = tmp_path / "broken.aa2m"
    path.write_text(BROKEN, encoding="utf-8")
    uri = path.as_uri()
    workspace = SourceWorkspace()
    workspace.open(uri, BROKEN, 1)
    analyze_workspace(workspace, uri, context)
    workspace.close(uri)
    assert workspace.poll_disk() == set()

    path.write_text(FIXED + "\n", encoding="utf-8")
    assert workspace.poll_disk() == {uri}
    analyze_workspace(workspace, uri, context)
    assert _codes(workspace, uri) == []

    path.write_text(BROKEN, encoding="utf-8")
    assert workspace.poll_disk() == {uri}
    analyze_workspace(workspace, uri, context)
    assert _codes(workspace, uri) == ["INT_OUT_OF_RANGE"]

    path.unlink()
    assert workspace.poll_disk() == {uri}
    assert workspace.root(uri) is None
    assert _codes(workspace, uri) == []
    assert workspace.poll_disk() == set()


def test_reopening_or_unsaved_files_are_not_retained(tmp_path, context):
    path = tmp_path / "broken.aa2m"
    path.write_text(BROKEN, encoding="utf-8")
    workspace = SourceWorkspace()
    workspace.open(path.as_uri(), BROKEN, 1)
    analyze_workspace(workspace, path.as_uri(), context)
    workspace.close(path.as_uri())

    workspace.open(path.as_uri(), FIXED, 2)
    analyze_workspace(workspace, path.as_uri(), context)
    assert _codes(workspace, path.as_uri()) == []

    for uri in ((tmp_path / "missing.aa2m").as_uri(), "untitled:Untitled-1"):
        workspace.open(uri, BROKEN, 1)
        analyze_workspace(workspace, uri, context)
        assert workspace.close(uri) == set()
        assert workspace.root(uri) is None
        assert _codes(workspace, uri) == []
