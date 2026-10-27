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
    arguments, _ = arguments_for(tmp_path, command)

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


@pytest.mark.parametrize("command", ("validate", "compile", "decompile"))
def test_policy_configuration_failure_is_internal_error(command, tmp_path, monkeypatch, capsys):
    arguments, _ = arguments_for(tmp_path, command)
    policy = tmp_path / "policy.toml"
    policy.write_text('language_version = "wrong"\n', encoding="utf-8")
    monkeypatch.setattr(policy_loader, "language_policy_path", lambda: policy)

    assert main(arguments) == EXIT_INTERNAL_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "metadata error:" in captured.err and str(policy) in captured.err


UNSUPPORTED_BINARY = encode_module(
    Module(
        "Mismatch",
        globals=(GlobalVariable(ValueType.INT, "x", Value.boolean(True), Value.integer(0)),),
    )
)


@pytest.mark.parametrize(
    ("command", "files", "target", "message"),
    [
        ("compile", {"input.aa2m": b'module "M" {'}, "input.aa2m", "error[SYNTAX_ERROR]"),
        (
            "compile",
            {"input.aa2m": b'module "M" { trigger "T" { let x: string = ThisCard(); } }'},
            "input.aa2m",
            "error[SOURCE_TYPE_MISMATCH]",
        ),
        (
            "compile",
            {"input.aa2m": b'import "lib.aa2mi"; module "M" {}', "lib.aa2mi": b"\xff"},
            "input.aa2m",
            "error[IMPORT_ENCODING]",
        ),
        (
            "compile",
            {"lib.aa2mi": b'macro work {} module "M" {}'},
            "lib.aa2mi",
            "error[LIBRARY_COMPILE]",
        ),
        ("compile", {"input.aa2m": b"\xff"}, "input.aa2m", "source is not valid UTF-8: {target}"),
        ("decompile", {"INPUT": b"\x01\x02"}, "INPUT", "error[DECODE_ERROR]"),
        ("decompile", {"INPUT": UNSUPPORTED_BINARY}, "INPUT", "cannot preserve"),
    ],
    ids=[
        "syntax-error",
        "binding-error",
        "import-encoding",
        "library-compile",
        "source-not-utf8",
        "binary-decode-error",
        "unsupported-decompilation",
    ],
)
def test_failed_command_is_input_error_and_keeps_existing_output(
    command, files, target, message, tmp_path, capsys
):
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    output = tmp_path / "output"
    output.write_bytes(b"preserve existing output")
    path = tmp_path / target

    assert main([command, str(path), "--output", str(output)]) == EXIT_INPUT_ERROR

    captured = capsys.readouterr()
    assert captured.out == ""
    assert message.format(target=path) in captured.err
    assert output.read_bytes() == b"preserve existing output"


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
def test_unreadable_input_is_input_error(command, tmp_path, monkeypatch, capsys):
    arguments, _ = arguments_for(tmp_path, command)
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
