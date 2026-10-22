"""The installed package runs without reading the source checkout."""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap

from tests.support.paths import MODULE_FIXTURES, ROOT


def test_runtime_uses_only_copied_package_and_packaged_resources(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    shutil.copytree(
        ROOT / "aa2modulus",
        runtime / "aa2modulus",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    fixture = runtime / "Race-Human"
    shutil.copyfile(MODULE_FIXTURES / "Race-Human", fixture)

    script = textwrap.dedent(
        """\
        import sys
        from pathlib import Path

        runtime, original = map(Path, sys.argv[1:])
        sys.path.insert(0, str(runtime))
        package = (runtime / "aa2modulus").resolve()
        opened_resources = set()

        def guard(event, args):
            if event != "open" or not args:
                return
            path = args[0]
            if isinstance(path, (str, bytes)):
                path = Path(path.decode() if isinstance(path, bytes) else path).resolve()
                if path.is_relative_to(original) and not path.is_relative_to(original / ".venv"):
                    raise AssertionError(f"runtime accessed original project: {path}")
                grammar = package / "syntax" / "grammar" / "unified.lark"
                policy = package / "language" / "policy.toml"
                if path.is_relative_to(package / "metadata" / "registry") or path in (
                    policy,
                    grammar,
                ):
                    opened_resources.add(path.relative_to(package).as_posix())

        sys.addaudithook(guard)
        from aa2modulus.binary.reader import decode_module
        from aa2modulus.metadata.loader import load_metadata
        from aa2modulus.model.values import Value
        from aa2modulus.cli.main import main

        assert Path(sys.modules["aa2modulus"].__file__).resolve().is_relative_to(runtime)
        assert not (runtime / "tools").exists()
        metadata = load_metadata()
        assert len(metadata.fingerprint) == 64

        library = runtime / "helpers.aa2mi"
        source = runtime / "module.aa2m"
        binary = runtime / "MODULE"
        library.write_text('macro "note" { param "message" string; WriteLog(message); }')
        source.write_text(
            'import "helpers.aa2mi"; module "Imported" { trigger "T" { note("hello"); } }'
        )
        assert main(["compile", str(source), "--output", str(binary)]) == 0
        assert binary.is_file()
        imported = decode_module(binary.read_bytes(), reject_trailing=True).module
        (write_log,) = imported.triggers[0].gui_actions
        assert write_log.action.id == 63
        assert write_log.action.parameters[0].constant == Value.string("hello")

        native = runtime / "Race-Human"
        recovered = runtime / "recovered.aa2m"
        recompiled = runtime / "RECOMPILED"
        assert main(["inspect", "--strict", str(native)]) == 0
        assert main(["decompile", str(native), "--output", str(recovered)]) == 0
        assert main(["compile", str(recovered), "--output", str(recompiled)]) == 0
        assert recompiled.read_bytes() == native.read_bytes()

        expected = {
            "metadata/registry/actions.json",
            "metadata/registry/events.json",
            "metadata/registry/expressions.json",
            "metadata/registry/manifest.json",
            "metadata/registry/named_constants.json",
            "language/policy.toml",
            "syntax/grammar/unified.lark",
        }
        assert opened_resources == expected, opened_resources
        for name, module in tuple(sys.modules.items()):
            if name == "aa2modulus" or name.startswith("aa2modulus."):
                assert Path(module.__file__).resolve().is_relative_to(runtime), name
        """
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(runtime), str(ROOT)],
        cwd=runtime,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
