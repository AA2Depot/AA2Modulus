"""Source diagnostics reach stderr with a located snippet or a one-line short form."""

from __future__ import annotations

from pathlib import Path

import pytest

from aa2modulus.cli.common import EXIT_INPUT_ERROR
from tests.support.cli import invoke_cli

# The oversized literal starts at column 21 of line 2.
SOURCE = 'module "M" {\n  global big: int = 9999999999999;\n}\n'


@pytest.mark.parametrize("command", ("validate", "compile"))
def test_diagnostic_location_stream_and_exit_code(command, tmp_path: Path, capsys):
    source = tmp_path / "big.aa2m"
    source.write_text(SOURCE, encoding="utf-8")
    arguments = [command, str(source)]
    if command == "compile":
        arguments.extend(("--output", str(tmp_path / "compiled-module")))

    human = invoke_cli(capsys, *arguments)

    assert human.returncode == EXIT_INPUT_ERROR
    assert human.stdout == ""
    assert "Traceback" not in human.stderr
    assert "error[INT_OUT_OF_RANGE]" in human.stderr
    assert f"--> {source}:2:21" in human.stderr
    assert "2 |   global big: int = 9999999999999;" in human.stderr

    short = invoke_cli(capsys, *arguments, "--diagnostic-format", "short")

    assert short.returncode == EXIT_INPUT_ERROR
    assert short.stdout == ""
    assert short.stderr.startswith(f"{source}:2:21: error[INT_OUT_OF_RANGE]: ")
