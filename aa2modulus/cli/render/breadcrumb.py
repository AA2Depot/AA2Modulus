"""Breadcrumbs: readable descriptions of structural paths in a decoded module."""

from __future__ import annotations

from collections.abc import Sequence

from ...core.diagnostics import Diagnostic
from ...model.records import Module
from .terminal import UNICODE_SEPARATOR


def _clean(text: str, limit: int = 40) -> str:
    text = "".join(ch if ch.isprintable() else "?" for ch in text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _template(template: str) -> str:
    return _clean(template.replace("%p", "…"), 60)


def _child(node: object, name: str, index: int | None = None) -> object | None:
    try:
        value = getattr(node, name)
        result: object = value if index is None else value[index]
        return result
    except (AttributeError, IndexError, TypeError):
        return None


def _metadata_name(node: object | None) -> str | None:
    metadata = getattr(node, "metadata", None)
    if metadata is None:
        return None
    return _template(metadata.interactive_name or metadata.name)


def breadcrumb(
    path: Sequence[str | int],
    *,
    module: Module | None = None,
    separator: str = UNICODE_SEPARATOR,
) -> str:
    """Describe a structural path readably, e.g. ``trigger "T" > If (...) > condition``.

    With the decoded ``module`` it names triggers, actions and expressions;
    without it, or where the path leaves the model, it falls back to field names
    and one-based indexes.
    """

    parts = list(path)
    if parts and parts[0] == "module":
        parts.pop(0)
    crumbs: list[str] = []
    node: object | None = module
    position = 0
    while position < len(parts):
        part = parts[position]
        following = parts[position + 1] if position + 1 < len(parts) else None
        if isinstance(part, str) and isinstance(following, int):
            position += 2
            node = _child(node, part, following) if node is not None else None
            crumbs.append(_collection_label(part, following, node))
            continue
        position += 1
        if part == "action" and node is not None and hasattr(node, "action"):
            node = _child(node, "action")
            continue
        if part == "action":
            continue
        if isinstance(part, str):
            node = _child(node, part) if node is not None else None
            crumbs.append(part.replace("_", " "))
        else:
            crumbs.append(f"[{part}]")
    return separator.join(crumbs) if crumbs else "module"


def unlocated_notes(diagnostic: Diagnostic, crumb: str) -> tuple[str, ...]:
    """Notes except ``in <place>`` context that the breadcrumb already shows."""

    return tuple(
        note
        for note in diagnostic.notes
        if not (note.startswith("in ") and note.removeprefix("in ") in crumb)
    )


def _collection_label(name: str, index: int, node: object | None) -> str:
    number = index + 1
    if name == "triggers":
        title = getattr(node, "name", None)
        return f'trigger "{_clean(title)}"' if isinstance(title, str) else f"trigger {number}"
    if name == "globals":
        title = getattr(node, "name", None)
        return f'global "{_clean(title)}"' if isinstance(title, str) else f"global {number}"
    if name == "variables":
        title = getattr(node, "name", None)
        return f'local "{_clean(title)}"' if isinstance(title, str) else f"local {number}"
    if name == "dependencies":
        return f'dependency "{_clean(node)}"' if isinstance(node, str) else f"dependency {number}"
    if name == "events":
        label = getattr(getattr(node, "metadata", None), "name", None)
        return _clean(label) if isinstance(label, str) else f"event {number}"
    if name in {"gui_actions", "children"}:
        label = _metadata_name(getattr(node, "action", None))
        return label or f"action {number}"
    if name == "parameters":
        label = _metadata_name(node)
        return f"parameter {number}" + (f": {label}" if label else "")
    return f"{name.replace('_', ' ')} {number}"
