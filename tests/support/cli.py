"""Helpers for exercising the packaged command line in subprocesses."""

from __future__ import annotations

import subprocess
import sys

from tests.support.paths import ROOT


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aa2modulus", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
