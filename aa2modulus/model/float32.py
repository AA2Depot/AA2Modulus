"""Exact IEEE-754 binary32 conversions."""

from __future__ import annotations

import struct
from typing import cast

from .types import ModelError


def float32_bits(value: float) -> int:
    """Return the exact little-endian IEEE-754 binary32 bits for ``value``."""

    if not isinstance(value, float):
        raise TypeError("float32 values require a float payload")
    try:
        return cast(int, struct.unpack("<I", struct.pack("<f", value))[0])
    except (OverflowError, struct.error) as exc:
        raise ModelError(f"float value is outside the binary32 range: {value!r}") from exc


def float32_from_bits(bits: int) -> float:
    """Construct a Python float from exact little-endian binary32 bits."""

    if isinstance(bits, bool) or not isinstance(bits, int) or not 0 <= bits <= 0xFFFFFFFF:
        raise ValueError("float32 bits must be an unsigned 32-bit integer")
    return cast(float, struct.unpack("<f", struct.pack("<I", bits))[0])


def is_unusual_float32(value: float) -> bool:
    """Return whether a float needs explicit bit syntax for source recovery."""

    return is_unusual_float32_bits(float32_bits(value))


def is_unusual_float32_bits(bits: int) -> bool:
    """Return whether binary32 bits need explicit source recovery syntax."""

    if isinstance(bits, bool) or not isinstance(bits, int) or not 0 <= bits <= 0xFFFFFFFF:
        raise ValueError("float32 bits must be an unsigned 32-bit integer")
    exponent = (bits >> 23) & 0xFF
    fraction = bits & 0x7FFFFF
    return exponent == 0xFF or (exponent == 0 and fraction != 0) or bits == 0x80000000
