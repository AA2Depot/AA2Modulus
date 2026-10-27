"""Helpers for exercising the command line, in-process or as a real process."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import pytest

from aa2modulus.cli.main import main
from tests.support.paths import ROOT


@dataclass(frozen=True, slots=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def invoke_cli(capsys: pytest.CaptureFixture[str], *arguments: str) -> CliResult:
    """Run ``main(arguments)`` in this process; argparse exits become return codes.

    Streams are not terminals under ``capsys``, so ``--color auto`` stays plain.
    """

    try:
        returncode = main(list(arguments))
    except SystemExit as exit_info:
        returncode = int(exit_info.code or 0)
    captured = capsys.readouterr()
    return CliResult(returncode, captured.out, captured.err)


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aa2modulus", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
