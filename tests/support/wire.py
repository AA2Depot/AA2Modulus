"""Hand-packed little-endian wire primitives for native binary expectations."""

from __future__ import annotations

import struct


def pack_string(value: str) -> bytes:
    """A UTF-16LE string: its code-unit count, then the units (lone surrogates allowed)."""

    raw = value.encode("utf-16-le", errors="surrogatepass")
    return struct.pack("<I", len(raw) // 2) + raw


def pack_vector(*items: bytes) -> bytes:
    """A vector: its element count, then the packed elements."""

    return struct.pack("<I", len(items)) + b"".join(items)


def pack_expression(return_type: int, identifier: int, payload: bytes = b"") -> bytes:
    """An expression header: its return type scope and ID, then the packed payload."""

    return struct.pack("<ii", return_type, identifier) + payload
