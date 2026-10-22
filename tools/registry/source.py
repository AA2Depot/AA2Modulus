"""The pinned AAUnlimited checkout: revision, files and enum namespaces"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from . import cpp

REVISION = "312c658b256f41771a5488fbf79a677d7b4551a8"
TRIGGERS = "AAUnlimited/Functions/Shared/Triggers/"
EXTERNAL = "AAUnlimited/External/ExternalClasses/"

# Registry tables and headers the generator parses.
FILES = (
    TRIGGERS + "Actions.cpp",
    TRIGGERS + "Actions.h",
    TRIGGERS + "Event.cpp",
    TRIGGERS + "Event.h",
    TRIGGERS + "Expressions.cpp",
    TRIGGERS + "Expressions.h",
    TRIGGERS + "NamedConstant.cpp",
    TRIGGERS + "NamedConstant.h",
    TRIGGERS + "Value.h",
)

# Enum namespaces a named-constant value may reference: namespace -> (file, enum).
ENUMS = {
    "Shared::Triggers::Events": (TRIGGERS + "Event.h", "Events"),
    "ExtClass::ConversationId": (EXTERNAL + "ConversationStruct.h", "ConversationId"),
    "ExtClass::PeriodId": (EXTERNAL + "TimeData.h", "PeriodId"),
    "ExtClass::DayName": (EXTERNAL + "TimeData.h", "DayName"),
    "ExtClass::PregnancyRisk": (EXTERNAL + "CharacterData.h", "PregnancyRisk"),
}
ENUM_FILES = tuple(sorted({file for file, _ in ENUMS.values()}))


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"cannot run git {' '.join(args)} in {root}: {error}") from error

    return result.stdout.strip()


def check_checkout(root: Path) -> None:
    """Require a clean checkout at the pinned revision."""

    revision = _git(root, "rev-parse", "HEAD")
    if revision != REVISION:
        raise RuntimeError(f"source revision {revision!r} is not the pinned {REVISION}")
    if _git(root, "status", "--porcelain"):
        raise RuntimeError("source checkout is dirty; generation requires a clean tree")


def _bytes(root: Path, relative: str) -> bytes:
    try:
        return (root / relative).read_bytes()
    except OSError as error:
        raise RuntimeError(f"cannot read source file {relative}: {error}") from error


def read(root: Path, relative: str) -> str:
    # Expressions.cpp contains Windows-1252 text.
    data = _bytes(root, relative)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def sha256(root: Path, relative: str) -> str:
    return hashlib.sha256(_bytes(root, relative)).hexdigest()


def enum_values(root: Path) -> dict[str, int]:
    """Qualified member -> value for every allowed enum namespace."""

    values: dict[str, int] = {}
    for namespace, (file, name) in ENUMS.items():
        for member, value in cpp.enum(read(root, file), name).items():
            qualified = f"{namespace}::{member}"
            if qualified in values:
                raise RuntimeError(f"duplicate pinned enum symbol: {qualified}")
            values[qualified] = value

    return values
