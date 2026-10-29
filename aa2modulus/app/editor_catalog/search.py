"""Ranked search over ``editor-data catalog`` entries."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_LOWER_UPPER = re.compile(r"([a-z0-9])([A-Z])")
_UPPER_WORD = re.compile(r"([A-Z]+)([A-Z][a-z])")
_SEPARATORS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class _Field:
    words: str
    compact: str
    weight: int


def search[T: Mapping[str, Any]](entries: Sequence[T], query: str) -> list[T]:
    """Entries matching every query token, best first; name matches outrank prose."""

    tokens = _words(query).split()
    if not tokens:
        return list(entries)
    compact = _compact(query)
    exact = query.strip().lower()
    scored: list[tuple[int, int, T]] = []
    for order, entry in enumerate(entries):
        names = [
            _field(entry["name"], 10),
            *(_field(alias, 8) for alias in entry["aliases"]),
            _field(entry["nativeName"], 6),
        ]
        fields = [*names, _field(entry["description"], 1)]
        score = 0
        for token in tokens:
            best = max(_field_score(token, item) for item in fields)
            if best == 0:
                break
            score += best
        else:
            # Whole-query phrase bonus on the compact forms ("StartHScene", "start h").
            for item in names:
                if item.compact == compact:
                    score += item.weight * 20
                elif compact in item.compact:
                    score += item.weight * 5
            if entry["name"].lower() == exact:
                score += 1000
            scored.append((-score, order, entry))
    scored.sort(key=lambda item: item[:2])
    return [entry for _, _, entry in scored]


def _words(value: str) -> str:
    """Lowercase words: punctuation separates, camelCase boundaries split."""

    value = _UPPER_WORD.sub(r"\1 \2", _LOWER_UPPER.sub(r"\1 \2", value))
    return _SEPARATORS.sub(" ", value.lower()).strip()


def _compact(value: str) -> str:
    return _SEPARATORS.sub("", value.lower())


def _field(value: str, weight: int) -> _Field:
    return _Field(_words(value), _compact(value), weight)


def _field_score(token: str, item: _Field) -> int:
    if item.words == token or item.compact == token:
        return item.weight * 3
    if f" {token}" in f" {item.words}":
        return item.weight * 2
    if token in item.words or token in item.compact:
        return item.weight
    return 0
