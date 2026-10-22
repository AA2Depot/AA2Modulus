"""Source operators: the fixed syntax table and policy operator definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from ..model.types import EXPR_PAYLOAD_MARKERS, TypeId, ValueType

Associativity = Literal["left", "right"]
Fixity = Literal["infix", "prefix"]

# token: (precedence, fixity, associativity, short_circuit)
OPERATOR_SYNTAX: Mapping[str, tuple[int, Fixity, Associativity, bool]] = MappingProxyType(
    {
        "||": (10, "infix", "left", True),
        "&&": (20, "infix", "left", True),
        "==": (30, "infix", "left", False),
        "!=": (30, "infix", "left", False),
        "<": (40, "infix", "left", False),
        "<=": (40, "infix", "left", False),
        ">": (40, "infix", "left", False),
        ">=": (40, "infix", "left", False),
        "+": (50, "infix", "left", False),
        "-": (50, "infix", "left", False),
        "*": (60, "infix", "left", False),
        "/": (60, "infix", "left", False),
        "!": (70, "prefix", "right", False),
    }
)


@dataclass(frozen=True, slots=True)
class OperatorDefinition:
    """A source operator mapped to one type-scoped AAUnlimited expression."""

    token: str
    expression_id: int
    return_type: TypeId
    parameter_types: tuple[TypeId, ...]
    precedence: int
    associativity: Associativity = "left"
    fixity: Fixity = "infix"
    short_circuit: bool = False
    source_name: str = ""

    def __post_init__(self) -> None:
        validate_operator_syntax(self)


def validate_operator_syntax(operator: OperatorDefinition) -> None:
    """Reject operator definitions the fixed lexer/parser/formatter cannot honor."""

    if not operator.token:
        raise ValueError("operator token cannot be empty")
    expected = OPERATOR_SYNTAX.get(operator.token)
    if expected is None:
        raise ValueError(f"operator token {operator.token!r} is unsupported by the source grammar")

    if operator.expression_id < 1:
        raise ValueError("operator expression_id must be positive")
    if operator.expression_id in EXPR_PAYLOAD_MARKERS:
        raise ValueError("operator expression_id cannot be a serialized payload marker")

    _validate_type(operator.return_type, "operator return_type")
    for index, parameter_type in enumerate(operator.parameter_types):
        _validate_type(parameter_type, f"operator parameters[{index}]")

    if operator.precedence < 1:
        raise ValueError("operator precedence must be positive")
    if operator.associativity not in ("left", "right"):
        raise ValueError("operator associativity must be 'left' or 'right'")
    if operator.fixity not in ("infix", "prefix"):
        raise ValueError("operator fixity must be 'infix' or 'prefix'")

    arity = 1 if operator.fixity == "prefix" else 2
    if len(operator.parameter_types) != arity:
        raise ValueError(f"{operator.fixity} operators require {arity} parameter type(s)")
    wanted_precedence, wanted_fixity, wanted_associativity, wanted_short_circuit = expected
    actual = (
        operator.precedence,
        operator.fixity,
        operator.associativity,
        operator.short_circuit,
    )
    wanted = (wanted_precedence, wanted_fixity, wanted_associativity, wanted_short_circuit)
    if actual != wanted:
        raise ValueError(
            f"operator {operator.token!r} syntax must use precedence/fixity/associativity/"
            f"short_circuit {wanted!r}, got {actual!r}"
        )


def _validate_type(value: int, label: str) -> None:
    if not 0 <= value < int(ValueType.N_TYPES):
        raise ValueError(f"{label} must be a supported type ID from 0 through 4")
