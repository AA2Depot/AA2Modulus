"""Fail-closed reading of C++ registry initializers, enums and literals

This is not a C++ parser. It skips comments and string literals, matches
delimiters and splits on top-level commas, which is enough for the pinned
registry tables. Anything it does not recognize raises RuntimeError.
"""

from __future__ import annotations

import re

PAIRS = {"{": "}", "(": ")", "[": "]"}
ESCAPES = {"\\": "\\", '"': '"', "'": "'", "n": "\n", "r": "\r", "t": "\t", "0": "\0", "?": "?"}

Entry = tuple[str, ...]


# Scanning


def _skip_string(text: str, index: int) -> int:
    quote = text[index]
    index += 1

    while index < len(text):
        if text[index] == "\\":
            index += 2
        elif text[index] == quote:
            return index + 1
        else:
            index += 1

    raise RuntimeError("unterminated C++ string or character literal")


def _skip_comment(text: str, index: int) -> int:
    if text.startswith("//", index):
        newline = text.find("\n", index + 2)
        return len(text) if newline < 0 else newline + 1

    end = text.find("*/", index + 2)
    if end < 0:
        raise RuntimeError("unterminated C++ block comment")
    return end + 2


def _is_comment(text: str, index: int) -> bool:
    return text.startswith(("//", "/*"), index)


def _skip(text: str, index: int) -> int | None:
    """Return the index after a comment or literal starting here, or None."""

    if _is_comment(text, index):
        return _skip_comment(text, index)
    if text[index] in ('"', "'"):
        return _skip_string(text, index)
    return None


def matching(text: str, start: int) -> int:
    """Index of the delimiter closing the one at ``start``."""

    opening = text[start]
    closing = PAIRS[opening]
    depth = 1
    index = start + 1

    while index < len(text):
        if (skipped := _skip(text, index)) is not None:
            index = skipped
            continue
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1

    raise RuntimeError(f"unterminated delimiter {opening}")


def split(text: str) -> list[str]:
    """Split on commas outside any delimiters, comments or literals."""

    closing_to_opening = {value: key for key, value in PAIRS.items()}
    depths = dict.fromkeys(PAIRS, 0)
    parts: list[str] = []
    start = index = 0

    while index < len(text):
        if (skipped := _skip(text, index)) is not None:
            index = skipped
            continue

        char = text[index]
        if char in depths:
            depths[char] += 1
        elif char in closing_to_opening:
            depths[closing_to_opening[char]] -= 1
            if depths[closing_to_opening[char]] < 0:
                raise RuntimeError(f"unbalanced delimiter {char}")
        elif char == "," and not any(depths.values()):
            parts.append(text[start:index])
            start = index + 1
        index += 1

    if any(depths.values()):
        raise RuntimeError("unbalanced registry entry delimiters")

    parts.append(text[start:])
    return parts


def _without_comments(text: str) -> str:
    result: list[str] = []
    index = 0

    while index < len(text):
        if _is_comment(text, index):
            end = _skip_comment(text, index)
            result.append(" " * (end - index))
        elif text[index] in ('"', "'"):
            end = _skip_string(text, index)
            result.append(text[index:end])
        else:
            end = index + 1
            result.append(text[index])
        index = end

    return "".join(result)


def clean(text: str) -> str:
    """Remove comments and collapse whitespace."""

    return " ".join(_without_comments(text).split())


# Blocks


def initializer(text: str, anchor: str) -> str:
    """Body of the first ``{ ... }`` after ``anchor``."""

    start = text.find(anchor)
    if start < 0:
        raise RuntimeError(f"missing registry anchor: {anchor}")

    opening = text.find("{", start + len(anchor))
    if opening < 0:
        raise RuntimeError(f"missing initializer body after {anchor}")

    return text[opening + 1 : matching(text, opening)]


def _braced(value: str, label: str) -> str:
    """Body of a value that is exactly one ``{ ... }``."""

    opening = value.find("{")
    if opening < 0:
        raise RuntimeError(f"{label} contains a non-entry item: {value[:80]!r}")

    closing = matching(value, opening)
    if value[closing + 1 :].strip():
        raise RuntimeError(f"{label} entry has trailing text: {value[closing + 1 :]!r}")

    return value[opening + 1 : closing]


def entries(body: str, label: str) -> list[Entry]:
    """``{a, b}, {c, d}`` as field tuples."""

    return [tuple(split(_braced(raw.strip(), label))) for raw in split(body) if clean(raw)]


def grouped_entries(body: str, label: str) -> list[list[Entry]]:
    """``{{a, b}, ...}, {{c, d}, ...}`` as one entry list per group."""

    return [entries(_braced(raw.strip(), label), label) for raw in split(body) if clean(raw)]


def enum(text: str, name: str) -> dict[str, int]:
    """Members of ``enum name { ... }`` with C++ implicit numbering."""

    match = re.search(r"\benum\s+" + re.escape(name) + r"\s*\{", text)
    if match is None:
        raise RuntimeError(f"missing enum declaration: {name}")

    opening = text.find("{", match.start(), match.end())
    body = text[opening + 1 : matching(text, opening)]

    members: dict[str, int] = {}
    value = 0
    for raw in split(body):
        field = clean(raw)
        if not field:
            continue

        member, equals, explicit = (piece.strip() for piece in field.partition("="))
        if not re.fullmatch(r"[A-Za-z_]\w*", member):
            raise RuntimeError(f"invalid {name} member: {field!r}")
        if equals:
            try:
                value = int(explicit, 0)
            except ValueError as error:
                raise RuntimeError(f"unsupported {name} value: {field!r}") from error
        if member in members:
            raise RuntimeError(f"duplicate {name} member: {member}")

        members[member] = value
        value += 1

    return members


# Values


def string(field: str, label: str) -> str:
    """Concatenated string literals in ``field``, decoded."""

    literals: list[str] = []
    index = 0

    while index < len(field):
        if _is_comment(field, index):
            index = _skip_comment(field, index)
        elif field[index] == '"':
            end = _skip_string(field, index)
            literals.append(_decode(field[index + 1 : end - 1], label))
            index = end
        else:
            index += 1

    if not literals:
        raise RuntimeError(f"{label} does not contain a string literal: {field!r}")
    return "".join(literals)


def _decode(value: str, label: str) -> str:
    result: list[str] = []
    index = 0

    while index < len(value):
        if value[index] != "\\":
            result.append(value[index])
            index += 1
            continue

        index += 1
        if index >= len(value):
            raise RuntimeError(f"unterminated escape in {label}")
        escaped = value[index]

        if escaped in ESCAPES:
            result.append(ESCAPES[escaped])
            index += 1
        elif escaped == "x":
            match = re.match(r"[0-9A-Fa-f]{1,2}", value[index + 1 :])
            if match is None:
                raise RuntimeError(f"invalid hexadecimal escape in {label}")
            result.append(chr(int(match.group(), 16)))
            index += 1 + len(match.group())
        elif escaped in "uU":
            width = 4 if escaped == "u" else 8
            digits = value[index + 1 : index + 1 + width]
            if len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                raise RuntimeError(f"invalid Unicode escape in {label}")
            result.append(chr(int(digits, 16)))
            index += 1 + width
        elif escaped in "01234567":
            match = re.match(r"[0-7]{1,3}", value[index:])
            assert match is not None
            result.append(chr(int(match.group(), 8)))
            index += len(match.group())
        else:
            raise RuntimeError(f"unsupported C++ escape \\{escaped} in {label}")

    return "".join(result)


def symbol(field: str, symbols: dict[str, int], label: str) -> int:
    """A decimal or hex integer, or an enum member, optionally parenthesized or qualified."""

    value = clean(field)
    while value.startswith("(") and value.endswith(")") and matching(value, 0) == len(value) - 1:
        value = value[1:-1].strip()

    if re.fullmatch(r"[-+]?\d+", value):
        return int(value, 10)
    if re.fullmatch(r"0[xX][0-9A-Fa-f]+", value):
        return int(value, 16)
    if value in symbols:
        return symbols[value]
    if "::" in value and value.rsplit("::", 1)[-1] in symbols:
        return symbols[value.rsplit("::", 1)[-1]]

    raise RuntimeError(f"unknown {label} symbol: {value!r}")


def symbol_list(field: str, symbols: dict[str, int], label: str) -> list[int]:
    """``{A, B}`` as a list of symbol values."""

    value = _without_comments(field).strip()
    if not value.startswith("{"):
        raise RuntimeError(f"expected {{ expression, got: {value[:80]!r}")

    end = matching(value, 0)
    if value[end + 1 :].strip():
        raise RuntimeError(f"mismatched {{ expression: {value[:80]!r}")

    return [symbol(part, symbols, label) for part in split(value[1:end]) if clean(part)]
