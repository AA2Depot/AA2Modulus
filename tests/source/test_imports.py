"""Filesystem imports compose source libraries as an author expects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa2modulus.app.compile import CompileError, compile_source, validate_source
from aa2modulus.context.limits import SourceLimits
from aa2modulus.syntax.parser.units import parse_library_source
from tests.support.source import parse_module


def _write(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")


def _root(imports: str, statements: str = "") -> str:
    return f'{imports}\nmodule "M" {{ trigger "T" {{ {statements} }} }}'


def test_transitive_diamond_imports_expand_to_hand_written_source(tmp_path):
    _write(tmp_path / "a.aa2mi", 'import "common.aa2mi"; macro outer { param x string; inner(x); }')
    _write(tmp_path / "b.aa2mi", 'import "common.aa2mi";')
    _write(tmp_path / "common.aa2mi", "macro inner { param x string; WriteLog(x); }")
    source = _root('import "a.aa2mi"; import "b.aa2mi";', 'outer("from a"); inner("from b");')
    hand = _root("", 'WriteLog("from a"); WriteLog("from b");')
    assert parse_module(source, import_base=tmp_path).to_ir() == parse_module(hand).to_ir()
    assert compile_source(source, import_base=tmp_path) == compile_source(hand)


def test_import_context_reads_current_library_text_on_each_compile(tmp_path):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    source = _root('import "lib.aa2mi";', "log();")
    _write(library, 'macro log { WriteLog("first"); }')
    first = compile_source(source, filename=str(root), import_base=tmp_path)
    _write(library, 'macro log { WriteLog("changed"); }')
    second = compile_source(source, filename=str(root), import_base=tmp_path)
    assert first != second
    assert second == compile_source(_root("", 'WriteLog("changed");'))


def test_import_cycle_and_duplicate_export_report_the_library_source(tmp_path):
    _write(tmp_path / "a.aa2mi", 'import "b.aa2mi"; macro first {}')
    _write(tmp_path / "b.aa2mi", 'import "a.aa2mi"; macro second {}')
    cycle = validate_source(
        _root('import "a.aa2mi";'), filename=str(tmp_path / "root.aa2m"), import_base=tmp_path
    )
    assert cycle.errors[0].code == "IMPORT_CYCLE"
    assert cycle.errors[0].filename == str((tmp_path / "b.aa2mi").resolve())

    _write(tmp_path / "a.aa2mi", "macro log {}")
    collision = validate_source(
        "macro LOG {} " + _root('import "a.aa2mi";'),
        filename=str(tmp_path / "root.aa2m"),
        import_base=tmp_path,
    )
    assert collision.errors[0].code == "DUPLICATE_MACRO"


def test_imported_syntax_error_keeps_library_location_and_import_origin(tmp_path):
    library = tmp_path / "broken.aa2mi"
    _write(library, "macro emit {\n  @\n}")
    result = validate_source(
        _root('import "broken.aa2mi";'), filename=str(tmp_path / "root.aa2m"), import_base=tmp_path
    )
    diagnostic = result.errors[0]
    assert (diagnostic.code, diagnostic.filename, diagnostic.line, diagnostic.column) == (
        "SYNTAX_ERROR",
        str(library.resolve()),
        2,
        3,
    )
    assert any(note.span.filename == str(tmp_path / "root.aa2m") for note in diagnostic.related)


def test_import_graph_depth_and_size_limits_reject_before_expansion(tmp_path):
    _write(tmp_path / "a.aa2mi", 'import "b.aa2mi";')
    _write(tmp_path / "b.aa2mi", 'macro log { WriteLog("x"); }')
    source = _root('import "a.aa2mi";')
    depth = validate_source(
        source, import_base=tmp_path, source_limits=SourceLimits(max_import_depth=1)
    )
    assert depth.errors[0].code == "IMPORT_DEPTH_LIMIT"
    files = validate_source(
        source, import_base=tmp_path, source_limits=SourceLimits(max_import_files=1)
    )
    assert files.errors[0].code == "IMPORT_FILE_LIMIT"
    total = validate_source(
        source,
        import_base=tmp_path,
        source_limits=SourceLimits(max_total_source_chars=len(source)),
    )
    assert total.errors[0].code == "IMPORT_SIZE_LIMIT"


def test_library_validation_and_compile_contract():
    library = "macro log { param message string; WriteLog(message); }"
    assert parse_library_source(library).module is None
    assert validate_source(library, source_kind="library").is_valid
    with pytest.raises(CompileError, match="MODULE_REQUIRED"):
        compile_source(library)


def test_canonical_and_symlink_imports_are_one_library(tmp_path):
    library = tmp_path / "lib.aa2mi"
    _write(library, 'macro log { WriteLog("hello"); }')
    alias = tmp_path / "alias.aa2mi"
    try:
        alias.symlink_to(library)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks are unavailable")
    source = _root('import "lib.aa2mi"; import "./alias.aa2mi";', "log();")
    hand = _root("", 'WriteLog("hello");')
    assert compile_source(source, import_base=tmp_path) == compile_source(hand)


@pytest.mark.parametrize("path", ["", "bad.aa2m", "MODULE", "nul\x00.aa2mi", "file.AA2MI"])
def test_invalid_import_paths_are_rejected_as_source_input(tmp_path, path):
    source = _root(f"import {json.dumps(path)};")
    result = validate_source(source, import_base=tmp_path)
    assert result.errors[0].code == "IMPORT_PATH"


def test_cached_diamond_uses_longest_path_and_aggregate_budgets(tmp_path):
    _write(tmp_path / "shared.aa2mi", 'macro log { WriteLog("x"); }')
    _write(tmp_path / "left.aa2mi", 'import "shared.aa2mi";')
    _write(tmp_path / "right.aa2mi", 'import "left.aa2mi";')
    source = _root('import "shared.aa2mi"; import "right.aa2mi";', "log();")
    assert validate_source(
        source, import_base=tmp_path, source_limits=SourceLimits(max_import_depth=3)
    ).is_valid
    depth = validate_source(
        source, import_base=tmp_path, source_limits=SourceLimits(max_import_depth=2)
    )
    assert depth.errors[0].code == "IMPORT_DEPTH_LIMIT"
    size = validate_source(
        source,
        import_base=tmp_path,
        source_limits=SourceLimits(max_total_source_chars=len(source) + 1),
    )
    assert size.errors[0].code == "IMPORT_SIZE_LIMIT"
    nodes = validate_source(
        source,
        import_base=tmp_path,
        source_limits=SourceLimits(max_nodes=8),
    )
    assert nodes.errors[0].code == "SOURCE_NODE_LIMIT"
