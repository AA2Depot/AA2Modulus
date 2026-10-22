"""Build tool"""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aa2modulus.language.loader import LANGUAGE_POLICY
from aa2modulus.version import __version__
from tools.standalone.notices import write_notices
from tools.standalone.verify import verify

PYINSTALLER_VERSION = "6.22.3"
EXECUTABLE = "aa2modulus.exe" if sys.platform == "win32" else "aa2modulus"
OUTPUTS = (EXECUTABLE, "LICENSE.txt", "THIRD_PARTY_NOTICES.txt", "SHA256SUMS", "README.txt")
# PyInstaller needs a script; the package's own __main__ uses a relative import.
ENTRY = "from aa2modulus.cli.main import main\n\nraise SystemExit(main())\n"


def target() -> str:
    machine = platform.machine().lower()

    if sys.platform not in {"linux", "win32"} or machine not in {"x86_64", "amd64"}:
        raise ValueError("standalone builds support native x64 Linux and Windows only")
    if sys.maxsize <= 2**32:
        raise ValueError("standalone builds require a 64-bit Python interpreter")

    return "windows-x64" if sys.platform == "win32" else "linux-x64"


def resources() -> list[Path]:
    """Runtime data files to bundle"""

    return [
        ROOT / "aa2modulus/syntax/grammar/unified.lark",
        ROOT / "aa2modulus/language" / LANGUAGE_POLICY,
        *sorted((ROOT / "aa2modulus/metadata/registry").glob("*.json")),
    ]


def build(output: Path) -> Path:
    name = target()

    try:
        installed = version("pyinstaller")
    except PackageNotFoundError as error:
        raise ValueError("run with the locked build group (uv run --group build)") from error
    if installed != PYINSTALLER_VERSION:
        raise ValueError(f"build requires PyInstaller {PYINSTALLER_VERSION}, found {installed}")

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    # Remove first so a failed build cannot leave notices and hashes of the old one.
    for file in OUTPUTS:
        (output / file).unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="aa2modulus-build-") as temporary:
        work = Path(temporary)
        entry = work / "entry.py"
        entry.write_text(ENTRY, encoding="utf-8")
        command = [
            sys.executable, "-m", "PyInstaller", "--onefile", "--console", "--noupx",
            "--name=aa2modulus", "--log-level=WARN", "--collect-data=lark",
            "--distpath", str(output), "--workpath", str(work), "--specpath", str(work),
            "--paths", str(ROOT),
        ]  # fmt: skip
        for path in resources():
            command += ["--add-data", f"{path}:{path.relative_to(ROOT).parent.as_posix()}"]
        subprocess.run([*command, str(entry)], cwd=ROOT, check=True)

    executable = output / EXECUTABLE
    verify(executable)

    shutil.copyfile(ROOT / "LICENSE", output / "LICENSE.txt")
    write_notices(output / "THIRD_PARTY_NOTICES.txt")

    (output / "SHA256SUMS").write_text(
        f"{hashlib.sha256(executable.read_bytes()).hexdigest()}  {executable.name}\n",
        encoding="utf-8",
    )

    launch = f".\\{EXECUTABLE}" if sys.platform == "win32" else f"./{EXECUTABLE}"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    (output / "README.txt").write_text(
        f"aa2modulus {__version__} — {name}\n\n"
        f"License: {project['license']}, see LICENSE.txt.\n"
        f"Source code: {project['urls']['Source']} (version {__version__}).\n\n"
        f"Run {launch} --help for compiler commands.\n"
        f"Editor launch: command=/absolute/path/{EXECUTABLE}, args=[lsp-server].\n"
        "The language server uses stdio; the editor owns its process.\n"
        "Register .aa2m and .aa2mi with language ID aa2m.\n",
        encoding="utf-8",
    )

    return executable


def main() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--output", type=Path, help="output directory (default: dist/<target>)")
    arguments = parser.parse_args()
    try:
        print(build(arguments.output or ROOT / "dist" / target()))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"build failed: {error}\n")


if __name__ == "__main__":
    main()
