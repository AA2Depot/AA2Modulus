"""Value types, expression payload markers and the model error."""

from __future__ import annotations

from enum import IntEnum

EXPR_CONSTANT = 1
EXPR_VAR = 2
EXPR_NAMEDCONSTANT = 3
EXPR_PAYLOAD_MARKERS = frozenset({EXPR_CONSTANT, EXPR_VAR, EXPR_NAMEDCONSTANT})
INT32_RANGE = range(-(2**31), 2**31)


class ModelError(ValueError):
    """Raised when a model object violates its structural invariants."""


class ValueType(IntEnum):
    INVALID = 0
    INT = 1
    BOOL = 2
    FLOAT = 3
    STRING = 4
    N_TYPES = 5


TypeId = int | ValueType
type ValuePayload = int | bool | float | str | None
