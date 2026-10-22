"""Third-party license notices for the standalone executable."""

from __future__ import annotations

import importlib.metadata
import sys
import sysconfig
from pathlib import Path

# Distributions bundled into the executable; PyInstaller for its bootloader.
DISTRIBUTIONS = (
    "attrs",
    "cattrs",
    "lark",
    "lsprotocol",
    "PyInstaller",
    "pygls",
    "typing-extensions",
)
LICENSE_NAMES = ("license", "licence", "copying", "notice")


def _read(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"license text is empty: {path}")
    return text


def _distribution_sections(name: str) -> list[tuple[str, str]]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError(f"bundled distribution is not installed: {name}") from error
    sections = []
    for entry in distribution.files or ():
        parts = [part.casefold() for part in entry.parts]
        if "licenses" in parts or parts[-1].startswith(LICENSE_NAMES):
            path = Path(str(distribution.locate_file(entry)))
            sections.append((f"{name} {distribution.version} — {entry.as_posix()}", _read(path)))
    if not sections:
        raise RuntimeError(f"no license text shipped with {name} {distribution.version}")
    return sections


def _python_section() -> tuple[str, str]:
    for base in (sysconfig.get_path("stdlib"), sys.base_prefix):
        path = Path(base) / "LICENSE.txt"
        if path.is_file():
            release = ".".join(str(part) for part in sys.version_info[:3])
            return f"Python {release} — LICENSE.txt", _read(path)
    raise RuntimeError("cannot locate the Python runtime's LICENSE.txt")


def write_notices(path: Path) -> Path:
    """Write the license texts of the build's Python runtime and bundled distributions."""

    sections = [_python_section()]
    for name in DISTRIBUTIONS:
        sections += _distribution_sections(name)
    parts = [
        (
            "Third-party notices for aa2modulus standalone builds\n\n"
            "These notices reproduce license texts shipped with the Python runtime and "
            "required runtime distributions.\n"
        )
    ]
    for title, body in sorted(sections, key=lambda section: (section[0].casefold(), section[0])):
        rule = "=" * len(title)
        parts.append(f"{rule}\n{title}\n{rule}\n\n{body}\n")
    path.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    return path
