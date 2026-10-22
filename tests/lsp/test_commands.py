"""Saved-file commands preserve exact binaries, input freshness, and recovery."""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from pygls.exceptions import JsonRpcContentModified, JsonRpcException, JsonRpcInvalidParams

from aa2modulus.app.compile import compile_source
from aa2modulus.binary.writer import encode_module
from aa2modulus.context.limits import SourceLimits
from aa2modulus.lsp.commands import compile as commands
from aa2modulus.lsp.commands import decompile, results
from aa2modulus.lsp.server.run import create_server
from aa2modulus.model.records import ActionCall, GuiAction, Module, Trigger
from tests.support.lsp_client import Client
from tests.support.paths import MODULE_FIXTURES
from tests.support.source import parse_module


@asynccontextmanager
async def _session(monkeypatch):
    server = create_server()
    monkeypatch.setattr(server, "text_document_publish_diagnostics", lambda params: None)
    server.start_workers()
    try:
        yield server
    finally:
        await server.stop_workers()


def _open(server, path, source, version=1, *, saved=True, library=False):
    if saved:
        path.write_text(source, encoding="utf-8", newline="")
    server.enqueue(
        server.sources.open(path.as_uri(), source, version, "aa2mi" if library else "aa2m")
    )


def _request(path, output=None, *, version=1):
    result = {"textDocument": {"uri": path.as_uri(), "version": version}}
    if output is not None:
        result["outputUri"] = output.as_uri()
    return result


def _no_staged(output):
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []


async def _wait_for_event(event: threading.Event, timeout: float = 3) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    loop = asyncio.get_running_loop()
    while not event.is_set() and loop.time() < deadline:
        await asyncio.sleep(0.01)
    return event.is_set()


def test_prepare_uses_current_overlay_graph_without_stale_edges_or_binding_errors(
    monkeypatch, tmp_path
):
    root = tmp_path / "root.aa2m"
    outer = tmp_path / "outer.aa2mi"
    old = tmp_path / "old.aa2mi"
    leaf = tmp_path / "leaf.aa2mi"
    outer.write_text('import "old.aa2mi";', encoding="utf-8")
    old.write_text("macro old {}", encoding="utf-8")
    leaf.write_text("macro leaf {}", encoding="utf-8")
    source = 'import "outer.aa2mi"; module "M" {}'

    async def run():
        async with _session(monkeypatch) as server:
            _open(server, root, source)
            first = await commands.prepare_compile(server, _request(root))
            assert first == {"dependencies": [outer.as_uri(), old.as_uri()], "diagnostics": []}
            _open(
                server,
                outer,
                'import "leaf.aa2mi"; macro broken { Missing(); }',
                saved=False,
                library=True,
            )
            alias = leaf.as_uri().replace("file:///", "file://localhost/", 1)
            server.enqueue(server.sources.open(alias, "macro leaf {}", 1, "aa2mi"))
            result = await commands.prepare_compile(server, _request(root))
            assert result == {"dependencies": [outer.as_uri(), alias], "diagnostics": []}
            assert str(old.resolve()) in server.sources.dependencies[root.as_uri()]
            assert server.sources.snapshots[root.as_uri()].analysis.result.errors

    asyncio.run(run())


@pytest.mark.parametrize(
    "root_source,library_source,limits,code",
    [
        ('module "M" { @ }', "", SourceLimits(), "SYNTAX_ERROR"),
        ('import "lib.aa2mi"; module "M" {}', None, SourceLimits(), "IMPORT_READ_ERROR"),
        ('import "lib.aa2mi"; module "M" {}', "macro", SourceLimits(), "SYNTAX_ERROR"),
        (
            'import "lib.aa2mi"; module "M" {}',
            "",
            SourceLimits(max_import_files=0),
            "IMPORT_FILE_LIMIT",
        ),
    ],
)
def test_prepare_reports_only_discovery_failures(
    monkeypatch, tmp_path, root_source, library_source, limits, code
):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    if library_source is not None:
        library.write_text(library_source, encoding="utf-8")

    async def run():
        async with _session(monkeypatch) as server:
            server.context = replace(server.context, source_limits=limits)
            _open(server, root, root_source)
            result = await commands.prepare_compile(server, _request(root))
            assert len(result["diagnostics"]) == 1
            assert result["diagnostics"][0]["severity"] == "error"
            assert code in result["diagnostics"][0]["message"]
            assert result["dependencies"] == ([library.as_uri()] if "import" in root_source else [])

    asyncio.run(run())


def test_compile_saved_transitive_sources_matches_exact_compiler_bytes(monkeypatch, tmp_path):
    root = tmp_path / "😀 saved module.aa2m"
    outer = tmp_path / "outer.aa2mi"
    leaf = tmp_path / "leaf.aa2mi"
    unrelated = tmp_path / "unrelated.aa2mi"
    output = tmp_path / "module output"
    source = 'import "outer.aa2mi"; module "M" { trigger "T" { emit(); } }\r\n'
    outer.write_text('import "leaf.aa2mi";', encoding="utf-8")
    leaf_source = 'macro emit { Notification("saved"); }'
    leaf.write_text(leaf_source, encoding="utf-8")
    expected = compile_source(source, filename=str(root.resolve()), import_base=tmp_path)

    async def run():
        async with _session(monkeypatch) as server:
            _open(server, root, source)
            _open(server, leaf, leaf_source, library=True)
            _open(server, unrelated, "macro broken { @ }", saved=False, library=True)
            result = await commands.compile_document(server, _request(root, output))
            assert result == {"compiled": True, "diagnostics": []}
            assert output.read_bytes() == expected
            assert not unrelated.exists()
            assert root.read_bytes().decode("utf-8") == source
            _no_staged(output)

    asyncio.run(run())


@pytest.mark.parametrize("dirty", ["root", "library"])
def test_compile_rejects_dirty_relevant_buffers_and_preserves_output(monkeypatch, tmp_path, dirty):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    output = tmp_path / "binary"
    source = 'import "lib.aa2mi"; module "M" { trigger "T" { emit(); } }'
    library.write_text('macro emit { Notification("disk"); }', encoding="utf-8")
    output.write_bytes(b"previous output")

    async def run():
        async with _session(monkeypatch) as server:
            _open(server, root, source)
            if dirty == "root":
                server.enqueue(
                    server.sources.change(root.as_uri(), source.replace('"M"', '"new"'), 2)
                )
                version = 2
            else:
                _open(
                    server,
                    library,
                    'macro emit { Notification("buffer"); }',
                    saved=False,
                    library=True,
                )
                version = 1
            with pytest.raises(JsonRpcContentModified, match="save this source"):
                await commands.compile_document(server, _request(root, output, version=version))
            assert output.read_bytes() == b"previous output"
            _no_staged(output)

    asyncio.run(run())


@pytest.mark.parametrize("target", ["root", "library", "hardlink", "symlink"])
def test_compile_never_overwrites_source_aliases(monkeypatch, tmp_path, target):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    source = 'import "lib.aa2mi"; module "M" {}'
    library.write_text("macro emit {}", encoding="utf-8")
    output = root if target == "root" else library
    if target in {"hardlink", "symlink"}:
        output = tmp_path / "alias"
        if target == "hardlink":
            output.hardlink_to(library)
        else:
            output.symlink_to(library)

    async def run():
        async with _session(monkeypatch) as server:
            _open(server, root, source)
            with pytest.raises(JsonRpcException, match="COMPILE_OUTPUT_SOURCE") as failure:
                await commands.compile_document(server, _request(root, output))
            assert failure.value.code == -32803
            assert root.read_text(encoding="utf-8") == source
            assert library.read_text(encoding="utf-8") == "macro emit {}"
            _no_staged(output)

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["compile", "stage"])
@pytest.mark.parametrize("changed", ["buffer", "disk"])
def test_compile_rechecks_imports_before_commit(monkeypatch, tmp_path, phase, changed):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    output = tmp_path / "binary"
    source = 'import "lib.aa2mi"; module "M" { trigger "T" { emit(); } }'
    library_source = 'macro emit { Notification("old"); }'
    library.write_text(library_source, encoding="utf-8")
    output.write_bytes(b"previous")
    started = threading.Event()
    release = threading.Event()
    attribute = "compile_source" if phase == "compile" else "_stage_output"
    original = getattr(commands, attribute)

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        started.set()
        assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(commands, attribute, delayed)

    async def run():
        async with _session(monkeypatch) as server:
            _open(server, root, source)
            _open(server, library, library_source, library=True)
            request = asyncio.create_task(commands.compile_document(server, _request(root, output)))
            try:
                assert await _wait_for_event(started)
                if changed == "buffer":
                    # Even an edit back to identical text is a renewed version.
                    server.enqueue(server.sources.change(library.as_uri(), library_source, 2))
                else:
                    # A same-size rewrite within one coarse timestamp tick keeps the
                    # (mtime, size, inode) signature; restoring mtime makes that certain.
                    before = library.stat()
                    library.write_text(library_source.replace("old", "new"), encoding="utf-8")
                    os.utime(library, ns=(before.st_atime_ns, before.st_mtime_ns))
                release.set()
                with pytest.raises(JsonRpcContentModified):
                    await request
                assert output.read_bytes() == b"previous"
                _no_staged(output)
            finally:
                release.set()

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["compile", "stage"])
def test_cancellation_leaves_no_output_or_temporary_files(monkeypatch, tmp_path, phase):
    root = tmp_path / "root.aa2m"
    output = tmp_path / "binary"
    source = 'module "M" {}'
    output.write_bytes(b"previous")
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    attribute = "compile_source" if phase == "compile" else "_stage_output"
    original = getattr(commands, attribute)

    def delayed(*args, **kwargs):
        try:
            result = original(*args, **kwargs)
            started.set()
            assert release.wait(timeout=5)
            return result
        finally:
            finished.set()

    monkeypatch.setattr(commands, attribute, delayed)

    async def run():
        cleaned = asyncio.Event()
        discard = commands._discard_staged

        def discarded(future):
            discard(future)
            cleaned.set()

        monkeypatch.setattr(commands, "_discard_staged", discarded)
        async with _session(monkeypatch) as server:
            _open(server, root, source)
            request = asyncio.create_task(commands.compile_document(server, _request(root, output)))
            try:
                assert await _wait_for_event(started)
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
                release.set()
                assert await _wait_for_event(finished)
                if phase == "stage":
                    await asyncio.wait_for(cleaned.wait(), 3)
                assert output.read_bytes() == b"previous"
                _no_staged(output)
            finally:
                release.set()

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["parse", "read", "write", "replace"])
def test_compilation_failures_preserve_previous_output(monkeypatch, tmp_path, failure):
    root = tmp_path / "root.aa2m"
    output = tmp_path / "binary"
    source = 'module "M" { @ }' if failure == "parse" else 'module "M" {}'
    output.write_bytes(b"previous")
    code = {
        "parse": "SYNTAX_ERROR",
        "read": "SOURCE_READ_ERROR",
        "write": "OUTPUT_WRITE_ERROR",
        "replace": "OUTPUT_WRITE_ERROR",
    }[failure]

    def denied(*args, **kwargs):
        raise OSError("permission denied")

    if failure == "write":
        monkeypatch.setattr(commands, "_stage_output", denied)
    elif failure == "replace":
        monkeypatch.setattr(commands.os, "replace", denied)

    async def run():
        async with _session(monkeypatch) as server:
            _open(server, root, source, saved=failure != "read")
            result = await commands.compile_document(server, _request(root, output))
            assert result["compiled"] is False
            assert result["diagnostics"][0]["severity"] == "error"
            assert code in result["diagnostics"][0]["message"]
            assert (
                str((output if failure in {"write", "replace"} else root).resolve())
                in result["diagnostics"][0]["message"]
            )
            if failure != "parse":
                assert "range" not in result["diagnostics"][0]
            assert output.read_bytes() == b"previous"
            _no_staged(output)

    asyncio.run(run())


@pytest.mark.parametrize("input_kind", ["stale", "library", "untitled", "closed"])
def test_compile_requires_current_open_saved_module(monkeypatch, tmp_path, input_kind):
    root = tmp_path / ("root.aa2mi" if input_kind == "library" else "root.aa2m")
    output = tmp_path / "binary"

    async def run():
        async with _session(monkeypatch) as server:
            value = _request(root, output, version=2 if input_kind == "stale" else 1)
            if input_kind == "untitled":
                uri = "untitled:Module"
                server.enqueue(server.sources.open(uri, 'module "M" {}', 1))
                value["textDocument"]["uri"] = uri
            elif input_kind != "closed":
                _open(server, root, "macro emit {}" if input_kind == "library" else 'module "M" {}')
            expected = JsonRpcContentModified if input_kind == "stale" else JsonRpcException
            with pytest.raises(expected):
                await commands.compile_document(server, value)
            assert not output.exists()
            _no_staged(output)

    asyncio.run(run())


def test_oversized_saved_source_reports_compiler_budget(monkeypatch, tmp_path):
    root = tmp_path / "root.aa2m"
    output = tmp_path / "binary"

    async def run():
        async with _session(monkeypatch) as server:
            server.context = replace(server.context, source_limits=SourceLimits(max_source_chars=8))
            _open(server, root, 'module "too large" {}')
            result = await commands.compile_document(server, _request(root, output))
            assert result["compiled"] is False
            assert "SOURCE_SIZE_LIMIT" in result["diagnostics"][0]["message"]
            assert not output.exists()

    asyncio.run(run())


def test_decompile_native_fixture_is_ready_for_exact_recompilation(monkeypatch):
    name = "Naive"
    data = (MODULE_FIXTURES / name).read_bytes()

    async def run():
        async with _session(monkeypatch) as server:
            result = await decompile.decompile_module_file(
                server, {"inputUri": (MODULE_FIXTURES / name).as_uri()}
            )
            assert all(item["severity"] == "warning" for item in result["diagnostics"])
            assert compile_source(result["source"]) == data

    asyncio.run(run())


def test_decompile_retains_raw_recovery_semantic_errors_and_trailing_warning(monkeypatch, tmp_path):
    path = tmp_path / "recovery"
    data = encode_module(
        Module("M", triggers=(Trigger("T", gui_actions=(GuiAction(ActionCall(901)),)),))
    )
    path.write_bytes(data + b"tail")

    async def run():
        async with _session(monkeypatch) as server:
            result = await decompile.decompile_module_file(server, {"inputUri": path.as_uri()})
            assert "action 901" in result["source"]
            assert encode_module(parse_module(result["source"])) == data
            assert any(
                item["severity"] == "error" and "UNKNOWN_ACTION" in item["message"]
                for item in result["diagnostics"]
            )
            assert result["diagnostics"][-1] == {
                "severity": "warning",
                "message": (
                    f"{path}@0x{len(data):X}: warning[TRAILING_BYTES]: "
                    "4 trailing bytes remain after the module data"
                ),
                "code": "TRAILING_BYTES",
                "detail": "4 trailing bytes remain after the module data",
            }

    asyncio.run(run())


def _range(start_line, start_character, end_line, end_character):
    return {
        "start": {"line": start_line, "character": start_character},
        "end": {"line": end_line, "character": end_character},
    }


def test_decompile_locates_findings_in_the_recovered_source(monkeypatch, tmp_path):
    path = tmp_path / "recovery"
    path.write_bytes(
        encode_module(
            Module("M", triggers=(Trigger("T", gui_actions=(GuiAction(ActionCall(901)),)),))
        )
    )

    async def run():
        async with _session(monkeypatch) as server:
            result = await decompile.decompile_module_file(server, {"inputUri": path.as_uri()})
            (finding,) = result["diagnostics"]
            line = result["source"].splitlines()[finding["range"]["start"]["line"]]
            assert line.strip() == "raw_action 901;"
            assert finding["range"] == _range(3, 4, 3, 19)
            assert finding["target"] == "recovered"
            assert "uri" not in finding
            assert finding["code"] == "UNKNOWN_ACTION"
            assert finding["detail"].startswith("unknown action id 901\nnote: ")

    asyncio.run(run())


@pytest.mark.parametrize("encoding,start", [("utf-16", 45), ("utf-32", 44), ("utf-8", 47)])
def test_compile_binding_error_is_located_in_the_negotiated_encoding(
    monkeypatch, tmp_path, encoding, start
):
    root = tmp_path / "root.aa2m"
    output = tmp_path / "binary"
    # The non-BMP character before the literal is 2 UTF-16 and 4 UTF-8 code units.
    source = 'module "M" {\n  global s: string = "\U0001f600"; global big: int = 99999999999;\n}\n'

    async def run():
        async with _session(monkeypatch) as server:
            server.encoding = encoding
            _open(server, root, source)
            result = await commands.compile_document(server, _request(root, output))
            assert result["compiled"] is False
            (finding,) = result["diagnostics"]
            assert finding["code"] == "INT_OUT_OF_RANGE"
            assert finding["target"] == "source"
            assert finding["uri"] == root.as_uri()
            assert finding["range"] == _range(1, start, 1, start + 11)
            assert str(root.resolve()) in finding["message"]
            assert str(root.resolve()) not in finding["detail"]
            assert not output.exists()

    asyncio.run(run())


def test_compile_locates_findings_in_imported_libraries(monkeypatch, tmp_path):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    output = tmp_path / "binary"
    library.write_text("macro emit {\n  Missing();\n}\n", encoding="utf-8")
    source = 'import "lib.aa2mi";\nmodule "M" { trigger "T" { emit(); } }\n'

    async def run():
        async with _session(monkeypatch) as server:
            _open(server, root, source)
            result = await commands.compile_document(server, _request(root, output))
            assert result["compiled"] is False
            finding = result["diagnostics"][0]
            assert finding["target"] == "source"
            assert finding["uri"] == library.as_uri()
            assert finding["range"]["start"] == {"line": 1, "character": 2}
            assert all(item["uri"] == root.as_uri() for item in finding.get("related", []))

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["missing", "malformed"])
def test_decompile_fatal_failures_have_no_source_result(monkeypatch, tmp_path, failure):
    path = tmp_path / "binary"
    if failure == "malformed":
        path.write_bytes(b"\x01")

    async def run():
        async with _session(monkeypatch) as server:
            with pytest.raises(JsonRpcException) as error:
                await decompile.decompile_module_file(server, {"inputUri": path.as_uri()})
            assert error.value.code == -32803
            assert str(path.resolve()) in str(error.value)
            assert (
                "BINARY_ERROR" in str(error.value)
                if failure == "malformed"
                else "DECOMPILE_ERROR" in str(error.value)
            )

    asyncio.run(run())


@pytest.mark.parametrize(
    "value", [None, [], {}, {"inputUri": "untitled:M"}, {"inputUri": "file:///tmp/%XX"}]
)
def test_decompile_validates_wire_arguments(monkeypatch, value):
    async def run():
        async with _session(monkeypatch) as server:
            with pytest.raises(JsonRpcInvalidParams):
                await decompile.decompile_module_file(server, value)

    asyncio.run(run())


def test_standard_execute_command_advertisement_and_wire_results(tmp_path):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    output = tmp_path / "binary"
    source = 'import "lib.aa2mi"; module "M" { trigger "T" { emit(); } }'
    root.write_text(source, encoding="utf-8")
    library.write_text('macro emit { Notification("saved"); }', encoding="utf-8")
    client = Client()
    try:
        supported = client.initialized["capabilities"]["executeCommandProvider"]["commands"]
        assert {
            results.PREPARE_COMPILE,
            results.COMPILE_DOCUMENT,
            results.DECOMPILE_MODULE,
        } <= set(supported)
        client.open(root.as_uri(), source)
        prepared = client.request(
            "workspace/executeCommand",
            {"command": results.PREPARE_COMPILE, "arguments": [_request(root)]},
        )
        assert prepared == {"dependencies": [library.as_uri()], "diagnostics": []}
        result = client.request(
            "workspace/executeCommand",
            {"command": results.COMPILE_DOCUMENT, "arguments": [_request(root, output)]},
        )
        assert result == {"compiled": True, "diagnostics": []}
        decompiled = client.request(
            "workspace/executeCommand",
            {"command": results.DECOMPILE_MODULE, "arguments": [{"inputUri": output.as_uri()}]},
        )
        assert decompiled["diagnostics"] == []
        assert compile_source(decompiled["source"]) == output.read_bytes()
        client.finish()
    finally:
        if client.process.poll() is None:
            client.process.terminate()
            client.process.wait(timeout=10)
