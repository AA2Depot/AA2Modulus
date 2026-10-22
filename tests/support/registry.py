"""Copy the shipped registry for focused loader-failure scenarios."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.support.paths import REGISTRY


def copied_registry(
    tmp_path: Path,
    edit: Callable[[dict[str, Any]], None],
    *,
    filename: str = "expressions.json",
) -> Path:
    """Copy package registry files, edit one JSON document, and return its directory."""

    target = tmp_path / "registry"
    shutil.copytree(REGISTRY, target)
    path = target / filename
    document = json.loads(path.read_text(encoding="utf-8"))
    edit(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return target
