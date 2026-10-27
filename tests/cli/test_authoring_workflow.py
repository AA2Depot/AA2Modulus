"""CLI compiles imported authoring sources into native module bytes."""

from __future__ import annotations

from aa2modulus.binary.reader import decode_module
from aa2modulus.model.values import Value
from tests.support.cli import invoke_cli


def test_cli_compiles_nested_libraries_with_hygiene_and_recovers_standalone_source(
    tmp_path, capsys
):
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
    validated = invoke_cli(capsys, "validate", str(source))
    compiled = invoke_cli(capsys, "compile", str(source), "-o", str(binary))
    assert validated.returncode == compiled.returncode == 0
    assert validated.stderr == compiled.stderr == ""
    assert validated.stdout == f"valid: {source}\n"
    assert compiled.stdout == f"compiled: {source} -> {binary}\n"

    module = decode_module(binary.read_bytes(), reject_trailing=True).module
    assert (module.name, module.description) == ("Card setup 😀", "Préparer la carte")
    (global_counter,) = module.globals
    assert global_counter.default_value == Value.string("outside")
    (trigger,) = module.triggers
    assert trigger.name == "Initialize"
    (local_counter,) = trigger.variables
    assert local_counter.name != global_counter.name
    notification, _ = [node.action for node in trigger.gui_actions]
    assert notification.parameters[0].constant == Value.string("初期値")

    recovered = tmp_path / "recovered.aa2m"
    result = invoke_cli(capsys, "decompile", str(binary), "-o", str(recovered))
    assert result.returncode == 0 and result.stderr == ""
    assert "macro " not in recovered.read_text(encoding="utf-8")
    recompiled = tmp_path / "RECOVERED"
    result = invoke_cli(capsys, "compile", str(recovered), "-o", str(recompiled))
    assert result.returncode == 0 and result.stderr == ""
    assert recompiled.read_bytes() == binary.read_bytes()
