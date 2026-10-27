"""CLI plumbing for the validation profile and for diagnostics on recovered source."""

from __future__ import annotations

from pathlib import Path

from aa2modulus.binary.writer import encode_module
from aa2modulus.model.records import Module
from tests.support.cli import invoke_cli
from tests.support.regression_data import (
    card_receiver_module,
    type_mismatch_module,
    undefined_variables_module,
)


def write_module(path: Path, module: Module) -> Path:
    path.write_bytes(encode_module(module))
    return path


def test_native_validation_profile_downgrades_errors_to_warnings(tmp_path: Path, capsys):
    mismatch = write_module(tmp_path / "mismatch", type_mismatch_module())

    strict = invoke_cli(capsys, "inspect", "--strict", str(mismatch))
    native = invoke_cli(
        capsys, "inspect", "--strict", "--validation-profile", "native", str(mismatch)
    )

    assert strict.returncode == 1
    assert "error[VARIABLE_TYPE_MISMATCH]" in strict.stdout
    assert native.returncode == 0, native.stderr
    assert "warning[VARIABLE_TYPE_MISMATCH]" in native.stdout


def test_native_validation_profile_still_rejects_undefined_variables(tmp_path: Path, capsys):
    receiver = write_module(tmp_path / "receiver", card_receiver_module())

    result = invoke_cli(
        capsys, "inspect", "--strict", "--validation-profile", "native", str(receiver)
    )

    assert result.returncode == 1
    assert "error[UNDEFINED_VARIABLE]" in result.stdout


def test_decompile_locates_semantic_errors_in_the_recovered_source(tmp_path: Path, capsys):
    module = write_module(tmp_path / "undefined-module", undefined_variables_module())
    output = tmp_path / "recovered.aa2m"

    result = invoke_cli(capsys, "decompile", str(module), "--output", str(output))

    assert result.returncode == 0
    assert result.stdout == f"decompiled: {module} -> {output}\n"
    assert output.read_text(encoding="utf-8").startswith('module "Undefined variables"')
    assert result.stderr.count("warning[UNDEFINED_VARIABLE]") == 2
    assert f"--> {output}:6:36" in result.stderr
    assert f"--> {output}:7:37" in result.stderr
    assert "offset 0x" not in result.stderr
    assert result.stderr.rstrip().endswith("declare the suggested globals before compiling")

    verbose = invoke_cli(capsys, "decompile", str(module), "-o", str(output), "--verbose")
    assert "= offset: 0x" in verbose.stderr and "= path: " in verbose.stderr

    printed = invoke_cli(capsys, "decompile", str(module), "--diagnostic-format", "short")
    assert printed.returncode == 0
    assert printed.stdout.startswith('module "Undefined variables"')
    assert "<stdout>:6:36: warning[UNDEFINED_VARIABLE]:" in printed.stderr
    assert "<stdout>:7:37: warning[UNDEFINED_VARIABLE]:" in printed.stderr

    compiled = invoke_cli(capsys, "compile", str(output), "--output", str(tmp_path / "compiled"))
    assert compiled.returncode == 1
    assert compiled.stdout == ""
    assert compiled.stderr.count("error[UNDEFINED_VARIABLE]") == 2
