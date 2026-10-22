"""Smoke check for a frozen executable

The test suite covers behavior before a build, so this only checks that the
executable starts and reports the source version.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from aa2modulus.version import __version__

TIMEOUT = 30
EXPECTED = f"aa2modulus {__version__}"


def run(executable: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            [str(executable), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{' '.join(args)} timed out") from error

    if result.returncode or result.stderr:
        raise RuntimeError(f"{' '.join(args)} exited {result.returncode}: {result.stderr[:1000]}")

    return result.stdout.strip()


def verify(executable: Path) -> None:
    """Raise if the CLI or the language-server entry point cannot run"""

    for args in (["--version"], ["lsp-server", "--version"]):
        output = run(executable, *args)
        if output != EXPECTED:
            raise RuntimeError(f"{' '.join(args)} printed {output!r}, expected {EXPECTED!r}")
