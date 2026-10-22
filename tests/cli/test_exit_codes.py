"""CLI failure classes keep distinct status codes, streams and file effects."""

from __future__ import annotations

from pathlib import Path

import pytest

from aa2modulus.binary.writer import encode_module
from aa2modulus.cli.common import EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR
from aa2modulus.cli.main import main
from aa2modulus.language import loader as policy_loader
from aa2modulus.metadata.schema import MetadataError
from aa2modulus.model.records import GlobalVariable, Module
from aa2modulus.model.types import ValueType
from aa2modulus.model.values import Value


def arguments_for(tmp_path: Path, command: str) -> tuple[list[str], Path]:
    source = tmp_path / "input.aa2m"
    source.write_text('module "M" {}', encoding="utf-8")
    binary = tmp_path / "INPUT"
    binary.write_bytes(encode_module(Module("M")))
    output = tmp_path / "output"
    arguments = [command, str(source if command in {"validate", "compile"} else binary)]
    if command in {"compile", "decompile"}:
        arguments.extend(("--output", str(output)))
    return arguments, output


@pytest.mark.parametrize("command", ("inspect", "validate", "compile", "decompile"))
def test_registry_configuration_failure_is_internal_error(command, tmp_path, monkeypatch, capsys):
    arguments, output = arguments_for(tmp_path, command)

    def broken_registry():
        raise MetadataError("broken registry")

    for command_module in ("inspect", "validate", "compile", "decompile"):
        monkeypatch.setattr(
            f"aa2modulus.cli.commands.{command_module}.load_metadata", broken_registry
        )
    monkeypatch.setattr("aa2modulus.context.operation.load_metadata", broken_registry)

    assert main(arguments) == EXIT_INTERNAL_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "metadata error: broken registry" in captured.err
    assert not output.exists()


@pytest.mark.parametrize("command", ("validate", "compile", "decompile"))
def test_policy_configuration_failure_is_internal_error(command, tmp_path, monkeypatch, capsys):
    arguments, output = arguments_for(tmp_path, command)
    policy = tmp_path / "policy.toml"
    policy.write_text('language_version = "wrong"\n', encoding="utf-8")
    monkeypatch.setattr(policy_loader, "language_policy_path", lambda: policy)

    assert main(arguments) == EXIT_INTERNAL_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "metadata error:" in captured.err and str(policy) in captured.err
    assert not output.exists()


def test_unsupported_decompilation_is_input_error(tmp_path, capsys):
    model = Module(
        "Mismatch",
        globals=(GlobalVariable(ValueType.INT, "x", Value.boolean(True), Value.integer(0)),),
    )
    binary = tmp_path / "INPUT"
    binary.write_bytes(encode_module(model))
    output = tmp_path / "recovered.aa2m"

    result = main(["decompile", str(binary), "--output", str(output)])

    captured = capsys.readouterr()
    assert result == EXIT_INPUT_ERROR
    assert captured.out == ""
    assert "cannot preserve" in captured.err
    assert not output.exists()


def test_unexpected_cli_programming_errors_propagate(tmp_path, monkeypatch):
    arguments, _ = arguments_for(tmp_path, "compile")

    def broken_compiler(*args, **kwargs):
        raise RuntimeError("compiler bug")

    monkeypatch.setattr(
        "aa2modulus.cli.commands.compile.compile_source_with_warnings", broken_compiler
    )
    with pytest.raises(RuntimeError, match="compiler bug"):
        main(arguments)


@pytest.mark.parametrize("command", ("inspect", "compile", "decompile"))
def test_unreadable_input_does_not_replace_output(command, tmp_path, monkeypatch, capsys):
    arguments, output = arguments_for(tmp_path, command)
    output.write_bytes(b"preserve")
    unreadable = Path(arguments[1])
    original_open = Path.open

    def deny_input(path, *args, **kwargs):
        if path == unreadable:
            raise PermissionError("access denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_input)
    assert main(arguments) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(unreadable) in captured.err and "access denied" in captured.err
    assert output.read_bytes() == b"preserve"


def test_invalid_utf8_source_does_not_replace_compile_output(tmp_path, capsys):
    arguments, output = arguments_for(tmp_path, "compile")
    Path(arguments[1]).write_bytes(b"\xff")
    output.write_bytes(b"preserve")

    assert main(arguments) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "source is not valid UTF-8" in captured.err
    assert arguments[1] in captured.err
    assert output.read_bytes() == b"preserve"


@pytest.mark.parametrize("command,description", (("compile", "module"), ("decompile", "source")))
def test_output_write_failure_keeps_input(command, description, tmp_path, capsys):
    arguments, _ = arguments_for(tmp_path, command)
    input_path = Path(arguments[1])
    original = input_path.read_bytes()
    output = tmp_path / "missing-parent" / "OUTPUT"
    arguments[-1] = str(output)

    assert main(arguments) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"could not write {description} {output}" in captured.err
    assert not output.exists()
    assert input_path.read_bytes() == original
