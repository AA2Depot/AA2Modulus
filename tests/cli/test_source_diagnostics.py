"""Representative syntax and binding diagnostics through both CLI paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support.cli import run_cli


@dataclass(frozen=True)
class DiagnosticCase:
    name: str
    source: str
    token: str
    code: str

    @property
    def line_column(self) -> tuple[int, int]:
        offset = self.source.index(self.token)
        return self.source.count("\n", 0, offset) + 1, offset - self.source.rfind("\n", 0, offset)


CLI_CASES = (
    DiagnosticCase("syntax-escape", 'module "Bad\\q" {}', '"Bad\\q"', "INVALID_STRING"),
    DiagnosticCase(
        "binding-return-type",
        'module "M" { trigger "T" { let x: string = ThisCard(); } }',
        "ThisCard",
        "SOURCE_TYPE_MISMATCH",
    ),
    DiagnosticCase(
        "int-out-of-range",
        'module "M" {\n  global big: int = 9999999999999;\n}\n',
        "9999999999999",
        "INT_OUT_OF_RANGE",
    ),
)


@pytest.mark.parametrize("case", CLI_CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("command", ("validate", "compile"))
def test_cli_diagnostic_location_stream_and_output(
    case: DiagnosticCase, command: str, tmp_path: Path
):
    source = tmp_path / f"{case.name}.aa2m"
    output = tmp_path / "compiled-module"
    source.write_text(case.source, encoding="utf-8")
    arguments = [command, str(source)]
    if command == "compile":
        arguments.extend(("--output", str(output)))

    result = run_cli(*arguments)

    line, column = case.line_column
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert f"--> {source}:{line}:{column}" in result.stderr
    assert f"error[{case.code}]" in result.stderr

    short = run_cli(*arguments, "--diagnostic-format", "short")
    assert re.search(
        rf"^{re.escape(str(source))}:{line}:{column}: error\[{re.escape(case.code)}\]: ",
        short.stderr,
        re.MULTILINE,
    )
    assert not output.exists()
