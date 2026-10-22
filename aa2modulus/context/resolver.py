"""How a source operation finds and reads imported libraries."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class SourceResolver(Protocol):
    """Resolve stable identities before reading at most max_chars + 1 characters.

    importer is None for imports in the root text; otherwise it is the canonical
    identity returned for the importing library. Providers own identity and
    relative-path semantics. OSError/UnicodeError are input failures; resolve's
    ValueError means an invalid path. Other provider exceptions propagate.
    """

    def resolve(self, path: str, *, importer: str | None) -> str: ...

    def read(self, identity: str, *, max_chars: int) -> str: ...


@dataclass(frozen=True, slots=True)
class FileSourceResolver:
    base: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", Path(self.base).resolve())

    def resolve(self, path: str, *, importer: str | None) -> str:
        base = self.base if importer is None else Path(importer).parent
        return os.path.normcase(str((base / path).resolve()))

    def read(self, identity: str, *, max_chars: int) -> str:
        with Path(identity).open(encoding="utf-8", newline="") as stream:
            return stream.read(min(max_chars + 1, sys.maxsize))
