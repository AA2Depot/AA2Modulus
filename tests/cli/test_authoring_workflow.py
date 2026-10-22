"""CLI compiles imported authoring sources into native module bytes."""

from __future__ import annotations

import pytest

from aa2modulus.binary.reader import decode_module
from aa2modulus.model.types import ValueType
from aa2modulus.model.values import Value
from tests.support.cli import run_cli


def test_cli_compiles_nested_libraries_with_hygiene_and_recovers_standalone_source(tmp_path):
    project = tmp_path / "project"
    libraries = project / "libraries"
    libraries.mkdir(parents=True)
    (libraries / "helpers.aa2mi").write_text(
        'macro "report" { param "label" string; Notification(label); }', encoding="utf-8"
    )
    (libraries / "initialize.aa2mi").write_text(
        """import "helpers.aa2mi";
        trigger "Start" {
          slot "tag" string;
          on CARD_ADDED;
          let counter: int = 2;
          report(tag);
          ClassStorage.SetInt(tag, counter);
        }""",
        encoding="utf-8",
    )
    source = project / "main.aa2m"
    source.write_text(
        """import "libraries/initialize.aa2mi";
        module "Card setup 😀" {
          description "Préparer la carte";
          global counter: string = "outside";
          import.trigger "Start" "Initialize" { slot "tag" = "初期値"; }
        }""".replace("\n", "\r\n"),
        encoding="utf-8",
    )
    binary = tmp_path / "CARD_SETUP"
    validated = run_cli("validate", str(source))
    compiled = run_cli("compile", str(source), "-o", str(binary))
    assert validated.returncode == compiled.returncode == 0
    assert validated.stderr == compiled.stderr == ""
    assert "valid:" in validated.stdout and "compiled:" in compiled.stdout

    module = decode_module(binary.read_bytes(), reject_trailing=True).module
    assert (module.name, module.description) == ("Card setup 😀", "Préparer la carte")
    (global_counter,) = module.globals
    assert (global_counter.name, global_counter.type) == ("counter", ValueType.STRING)
    assert global_counter.default_value == global_counter.current_value == Value.string("outside")
    (trigger,) = module.triggers
    assert trigger.name == "Initialize"
    assert [event.id for event in trigger.events] == [6]
    (local_counter,) = trigger.variables
    assert local_counter.name != global_counter.name
    assert local_counter.type is ValueType.INT
    assert local_counter.default_expression.constant == Value.integer(2)
    notification, storage = [node.action for node in trigger.gui_actions]
    assert (notification.id, storage.id) == (108, 110)
    assert [parameter.constant for parameter in notification.parameters] == [
        Value.string("初期値"),
        Value.boolean(False),
    ]
    assert storage.parameters[0].constant == Value.string("初期値")
    reference = storage.parameters[1]
    assert (reference.id, reference.return_type, reference.variable_name) == (
        2,
        ValueType.INT,
        local_counter.name,
    )

    recovered = tmp_path / "recovered.aa2m"
    result = run_cli("decompile", str(binary), "-o", str(recovered))
    assert result.returncode == 0 and result.stderr == ""
    recompiled = tmp_path / "RECOVERED"
    result = run_cli("compile", str(recovered), "-o", str(recompiled))
    assert result.returncode == 0 and result.stderr == ""
    assert recompiled.read_bytes() == binary.read_bytes()


def test_cli_import_encoding_failure_preserves_compiled_output(tmp_path):
    source = tmp_path / "root.aa2m"
    library = tmp_path / "lib.aa2mi"
    output = tmp_path / "MODULE"
    source.write_text('import "lib.aa2mi"; module "M" { trigger "T" { log(); } }', encoding="utf-8")
    library.write_text('macro log { WriteLog("ok"); }', encoding="utf-8")
    assert run_cli("compile", str(source), "--output", str(output)).returncode == 0
    previous = output.read_bytes()
    library.write_bytes(b"\xff")

    validated = run_cli("validate", str(source))
    compiled = run_cli("compile", str(source), "--output", str(output))

    assert validated.returncode == compiled.returncode == 1
    assert "IMPORT_ENCODING" in validated.stderr and validated.stdout == ""
    assert "IMPORT_ENCODING" in compiled.stderr
    assert output.read_bytes() == previous


def test_cli_rejects_compiling_library_with_embedded_module(tmp_path):
    library = tmp_path / "lib.aa2mi"
    output = tmp_path / "MODULE"
    library.write_text('macro work {} module "M" {}', encoding="utf-8")

    result = run_cli("compile", str(library), "--output", str(output))

    assert result.returncode == 1
    assert "LIBRARY_COMPILE" in result.stderr
    assert not output.exists()


def test_cli_macro_expansion_decompiles_without_macro_definitions(tmp_path):
    authored = tmp_path / "macros.aa2m"
    expanded = tmp_path / "expanded.aa2m"
    binary = tmp_path / "MODULE"
    recovered = tmp_path / "recovered.aa2m"
    authored.write_text(
        'macro "put" { param "key" string; param "value" int; '
        "ClassStorage.SetInt(key, value); }\n"
        'module "M" { trigger "T" { put("score", 7); } }',
        encoding="utf-8",
    )
    expanded.write_text(
        'module "M" { trigger "T" { ClassStorage.SetInt("score", 7); } }',
        encoding="utf-8",
    )

    authored_compile = run_cli("compile", str(authored), "--output", str(binary))
    expected_compile = run_cli("compile", str(expanded), "--output", str(tmp_path / "EXPECTED"))
    assert authored_compile.returncode == expected_compile.returncode == 0
    assert binary.read_bytes() == (tmp_path / "EXPECTED").read_bytes()
    decompiled = run_cli("decompile", str(binary), "--output", str(recovered))
    assert decompiled.returncode == 0
    assert "macro " not in recovered.read_text(encoding="utf-8")
    recompiled = run_cli("compile", str(recovered), "--output", str(tmp_path / "RECOVERED"))
    assert recompiled.returncode == 0
    assert (tmp_path / "RECOVERED").read_bytes() == binary.read_bytes()


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        (["--max-macro-nodes", "1"], "MACRO_EXPANSION_LIMIT"),
        (["--max-macro-depth", "0"], "MACRO_DEPTH_LIMIT"),
    ],
)
def test_cli_macro_expansion_failure_preserves_output(arguments, code, tmp_path):
    source = tmp_path / "source.aa2m"
    output = tmp_path / "MODULE"
    source.write_text(
        'macro "log" { WriteLog("x"); } module "M" { trigger "T" { log(); } }',
        encoding="utf-8",
    )
    output.write_bytes(b"existing output")

    result = run_cli("compile", str(source), "--output", str(output), *arguments)

    assert result.returncode == 1
    assert code in result.stderr
    assert output.read_bytes() == b"existing output"


def test_cli_macro_type_failure_keeps_related_note_and_writes_no_file(tmp_path):
    source = tmp_path / "bad.aa2m"
    output = tmp_path / "MODULE"
    source.write_text(
        'macro "m" { param "x" int; } module "M" { trigger "T" { m("bad"); } }',
        encoding="utf-8",
    )

    result = run_cli("compile", str(source), "--output", str(output))

    assert result.returncode == 1
    assert "SOURCE_TYPE_MISMATCH" in result.stderr
    assert "formal 'x' declared here" in result.stderr
    assert not output.exists()


def test_cli_template_expansion_limit_preserves_output(tmp_path):
    library = tmp_path / "lib.aa2mi"
    source = tmp_path / "root.aa2m"
    output = tmp_path / "OUTPUT"
    library.write_text(
        'trigger "T" { slot "x" int; ClassStorage.SetInt("a", x); }', encoding="utf-8"
    )
    source.write_text(
        'import "lib.aa2mi"; module "M" { import.trigger "T" { slot "x" = 1; } }',
        encoding="utf-8",
    )
    output.write_bytes(b"preserved")

    result = run_cli("compile", str(source), "--output", str(output), "--max-macro-nodes", "0")

    assert result.returncode == 1
    assert "TEMPLATE_EXPANSION_LIMIT" in result.stderr
    assert output.read_bytes() == b"preserved"
