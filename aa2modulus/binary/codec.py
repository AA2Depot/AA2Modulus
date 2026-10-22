"""Limit checks shared by the binary reader and writer."""

from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import DataclassInstance


def check_limit_fields(limits: DataclassInstance) -> None:
    """Every field of a codec limits dataclass is a nonnegative integer."""

    for item in fields(limits):
        value = getattr(limits, item.name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{item.name} must be an integer")
        if value < 0:
            raise ValueError(f"{item.name} cannot be negative")


class NodeBudget:
    """Counts decoded or encoded nodes against a limit before each node is handled."""

    def __init__(self, limit: int, counted: str, before: str) -> None:
        self.limit = limit
        self.counted = counted
        self.before = before
        self.used = 0

    def claim(self, kind: str) -> str | None:
        """Count one node, or return the limit message without counting it."""

        if self.used >= self.limit:
            return f"{self.counted} node limit of {self.limit} exceeded before {self.before} {kind}"
        self.used += 1
        return None
