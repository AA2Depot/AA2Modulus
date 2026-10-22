"""CLI scenarios for native validation and undeclared variables."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.model.records import Module
from tests.support.cli import run_cli
from tests.support.regression_data import (
    card_receiver_module,
    discarded_control_module,
    type_mismatch_module,
    undefined_variables_module,
)


def write_module(path: Path, module: Module) -> Path:
    path.write_bytes(encode_module(module))
    return path


def test_inspect_strict_and_native_profiles_report_different_severity(tmp_path: Path):
    mismatch = write_module(tmp_path / "mismatch", type_mismatch_module())
    strict = run_cli("inspect", "--strict", str(mismatch))
    native = run_cli("inspect", "--strict", "--validation-profile", "native", str(mismatch))

    assert strict.returncode == 1
    assert "error[VARIABLE_TYPE_MISMATCH]" in strict.stdout
    assert native.returncode == 0, native.stderr
    assert "warning[VARIABLE_TYPE_MISMATCH]" in native.stdout


def test_inspect_native_profile_preserves_dependency_records_and_downgrades_lint(tmp_path):
    module = write_module(tmp_path / "dependencies", Module("D", dependencies=("Z", "", "D", "Z")))
    strict = run_cli("inspect", "--strict", str(module))
    native = run_cli("inspect", "--strict", "--validation-profile", "native", str(module))

    assert strict.returncode == 1
    assert "error[INVALID_MODULE_DEPENDENCY]" in strict.stdout
    assert "error[DUPLICATE_MODULE_DEPENDENCY]" in strict.stdout
    assert native.returncode == 0, native.stderr
    assert "warning[INVALID_MODULE_DEPENDENCY]" in native.stdout
    assert "warning[DUPLICATE_MODULE_DEPENDENCY]" in native.stdout
    assert "Dependencies:\n  - Z\n  - \n  - D\n  - Z\n" in native.stdout


def test_inspect_native_controls_and_undefined_variables(tmp_path: Path):
    discarded = write_module(tmp_path / "discarded", discarded_control_module())
    strict_control = run_cli("inspect", "--strict", str(discarded))
    native_control = run_cli("inspect", "--validation-profile", "native", str(discarded))
    receiver = write_module(tmp_path / "receiver", card_receiver_module())
    missing = run_cli("inspect", "--validation-profile", "native", "--strict", str(receiver))

    assert strict_control.returncode == 1 and "UNDEFINED_VARIABLE" in strict_control.stdout
    assert native_control.returncode == 0 and "NATIVE_DISCARDED_CONTROL" in native_control.stdout
    assert missing.returncode == 1 and "UNDEFINED_VARIABLE" in missing.stdout


def test_dependency_name_does_not_supply_provider_globals(tmp_path: Path):
    receiver = write_module(
        tmp_path / "receiver", replace(card_receiver_module(), dependencies=("Provider",))
    )

    result = run_cli("inspect", "--strict", "--validation-profile", "native", str(receiver))

    assert result.returncode == 1
    assert "error[UNDEFINED_VARIABLE]" in result.stdout
    assert decode_module(receiver.read_bytes()).module.dependencies == ("Provider",)


def test_decompile_suggests_declaring_another_modules_global(tmp_path: Path):
    receiver = write_module(tmp_path / "receiver", card_receiver_module())
    declaration = "global external: int = 0;"

    decompiled = run_cli("decompile", str(receiver))

    assert decompiled.returncode == 0
    assert "warning[UNDEFINED_VARIABLE]" in decompiled.stderr
    assert "error[" not in decompiled.stderr
    assert f"help: declare it in this module: `{declaration}`" in decompiled.stderr
    assert 'raw_expression int 2 { variable "external"; }' in decompiled.stdout
    source = tmp_path / "receiver.aa2m"
    output = tmp_path / "compiled"
    source.write_text(
        decompiled.stdout.replace(
            'module "Receiver" {\n', f'module "Receiver" {{\n  {declaration}\n'
        ),
        encoding="utf-8",
    )
    compiled = run_cli("compile", str(source), "--output", str(output))

    assert compiled.returncode == 0, compiled.stderr
    recompiled = decode_module(output.read_bytes(), reject_trailing=True).module
    original = card_receiver_module()
    assert [item.name for item in recompiled.globals] == ["external"]
    assert recompiled.triggers[0].to_ir() == original.triggers[0].to_ir()


def test_decompile_locates_semantic_errors_in_the_recovered_source(tmp_path: Path):
    module = write_module(tmp_path / "undefined-module", undefined_variables_module())
    output = tmp_path / "recovered.aa2m"

    result = run_cli("decompile", str(module), "--output", str(output))

    assert result.returncode == 0
    assert result.stdout == f"decompiled: {module} -> {output}\n"
    assert output.read_text(encoding="utf-8").startswith('module "Undefined variables"')
    assert result.stderr.count("warning[UNDEFINED_VARIABLE]") == 2
    assert f"--> {output}:6:36" in result.stderr
    assert f"--> {output}:7:37" in result.stderr
    assert "offset 0x" not in result.stderr
    assert result.stderr.rstrip().endswith("declare the suggested globals before compiling")

    short = run_cli("decompile", str(module), "-o", str(output), "--diagnostic-format", "short")
    assert f"{output}:6:36: warning[UNDEFINED_VARIABLE]:" in short.stderr
    assert f"{output}:7:37: warning[UNDEFINED_VARIABLE]:" in short.stderr

    verbose = run_cli("decompile", str(module), "-o", str(output), "--verbose")
    assert "= offset: 0x" in verbose.stderr and "= path: " in verbose.stderr


def test_recovered_semantic_errors_do_not_create_or_replace_compile_output(tmp_path: Path):
    binary = write_module(tmp_path / "undefined-module", undefined_variables_module())
    recovered = tmp_path / "recovered.aa2m"
    decompiled = run_cli("decompile", str(binary), "--output", str(recovered))
    assert decompiled.returncode == 0
    source = tmp_path / "recovered-source.aa2m"
    source.write_bytes(recovered.read_bytes())

    for exists in (False, True):
        output = tmp_path / f"compiled-{exists}"
        if exists:
            output.write_bytes(b"preserve existing output")
        result = run_cli("compile", str(source), "--output", str(output))
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr.count("error[UNDEFINED_VARIABLE]") == 2
        assert output.read_bytes() == b"preserve existing output" if exists else not output.exists()


def test_recovered_undefined_source_is_rejected_by_validate(tmp_path: Path):
    binary = write_module(tmp_path / "undefined-module", undefined_variables_module())
    decompiled = run_cli("decompile", str(binary))
    source = tmp_path / "undefined.aa2m"
    source.write_text(decompiled.stdout, encoding="utf-8")

    result = run_cli("validate", str(source))

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.count("error[UNDEFINED_VARIABLE]") == 2
    assert "validation failed: 2 errors" in result.stderr
