"""Source spellings of native targets, and prose helpers, for validation messages."""

from __future__ import annotations

from typing import Literal

from ...language.catalog.model import LanguageCatalog
from ...metadata.snapshot import MetadataSnapshot
from ...model.control_flow import ACTION_FORLOOP, ACTION_SETVAR
from ...model.display import type_name
from ...model.records import Expression
from ...model.types import TypeId
from ...model.values import Value


def with_article(type_text: str) -> str:
    """``an int`` / ``a bool`` for diagnostic prose."""

    return f"{'an' if type_text[:1] in 'aeiou' else 'a'} {type_text}"


def or_list(items: list[str]) -> str:
    """``A``, ``A or B``, ``A, B, or C`` for diagnostic prose."""

    if len(items) <= 2:
        return " or ".join(items)
    return f"{', '.join(items[:-1])}, or {items[-1]}"


def value_text(value: Value) -> str:
    """A reviewed fallback literal as source text."""

    if isinstance(value.value, bool):
        return "true" if value.value else "false"
    return str(value.value)


class Labels:
    """Names targets the way an author writes them, falling back to raw forms."""

    def __init__(self, metadata: MetadataSnapshot, catalog: LanguageCatalog | None) -> None:
        self.metadata = metadata
        self.catalog = catalog

    def source(
        self, kind: Literal["action", "event", "expression"], identifier: int, scope: TypeId = 0
    ) -> str:
        """The canonical source spelling, else the raw form an author would write."""

        if self.catalog is not None:
            name = self.catalog.canonical_name(
                kind, identifier, scope if kind == "expression" else None
            )
            if name:
                return name
        if kind == "expression":
            return f"raw_expression {type_name(scope)} {identifier}"
        return f"raw_{kind} {identifier}"

    def native_note(
        self, kind: Literal["action", "event", "expression"], identifier: int, scope: TypeId = 0
    ) -> tuple[str, ...]:
        """The AAUnlimited GUI label, for searching the native editor."""

        metadata = (
            self.metadata.action(identifier)
            if kind == "action"
            else self.metadata.event(identifier)
            if kind == "event"
            else self.metadata.expression(scope, identifier)
        )
        if metadata is None or not metadata.name:
            return ()
        if metadata.name == self.source(kind, identifier, scope):
            return ()
        return (f"native name: {metadata.name!r}",)

    def expression(self, expression: Expression) -> str:
        return self.source("expression", expression.id, expression.return_type)

    def event(self, event_id: int) -> str:
        return self.source("event", event_id)

    def action(self, action_id: int) -> str:
        """Assignment and ``for`` are syntax, not named actions."""

        if action_id == ACTION_SETVAR:
            return "assignment"
        if action_id == ACTION_FORLOOP:
            return "`for` loop"
        return self.source("action", action_id)
