"""Source control flow and operator precedence match hand-written native records."""

from __future__ import annotations

from aa2modulus.app.compile import compile_source
from aa2modulus.binary.writer import encode_module
from aa2modulus.model.records import (
    ActionCall,
    Event,
    Expression,
    GuiAction,
    Module,
    Trigger,
    Variable,
)
from aa2modulus.model.types import EXPR_CONSTANT, EXPR_VAR, ValueType
from aa2modulus.model.values import Value
from tests.support.source import parse_module


def _constant(value: bool | int | str, value_type: ValueType) -> Expression:
    payload = {
        ValueType.BOOL: Value.boolean,
        ValueType.INT: Value.integer,
        ValueType.STRING: Value.string,
    }[value_type](value)
    return Expression(value_type, EXPR_CONSTANT, constant=payload)


def _operator(result: ValueType, identifier: int, *operands: Expression) -> Expression:
    return Expression(result, identifier, parameters=tuple(operands))


def test_branches_loops_and_for_compile_to_hand_built_native_tree():
    source = """module "Flow" {
      trigger "T" {
        on CARD_ADDED;
        let i: int = 0;
        if true { break; } else if false { continue if true; } else {}
        loop { break; continue if false; }
        for i from 0 to 2 { Notification("for"); }
      }
    }"""
    i = Expression(ValueType.INT, EXPR_VAR, variable_name="i")

    def truth(value):
        return _constant(value, ValueType.BOOL)

    notification = GuiAction(ActionCall(108, (_constant("for", ValueType.STRING), truth(False))))
    expected = Module(
        "Flow",
        triggers=(
            Trigger(
                "T",
                events=(Event(6),),
                variables=(Variable(ValueType.INT, "i", _constant(0, ValueType.INT)),),
                gui_actions=(
                    GuiAction(
                        ActionCall(2, (truth(True),)), (GuiAction(ActionCall(7, (truth(True),))),)
                    ),
                    GuiAction(
                        ActionCall(3, (truth(False),)), (GuiAction(ActionCall(8, (truth(True),))),)
                    ),
                    GuiAction(ActionCall(4)),
                    GuiAction(
                        ActionCall(6),
                        (
                            GuiAction(ActionCall(7, (truth(True),))),
                            GuiAction(ActionCall(8, (truth(False),))),
                        ),
                    ),
                    GuiAction(
                        ActionCall(
                            9, (i, _constant(0, ValueType.INT), _constant(2, ValueType.INT))
                        ),
                        (notification,),
                    ),
                ),
            ),
        ),
    )
    assert parse_module(source) == expected
    assert compile_source(source) == encode_module(expected)


def test_operator_precedence_compiles_to_hand_built_operand_tree():
    source = 'module "Ops" { trigger "T" { let result: bool = !true || 1 + 2 * 3 < 8 && 2 == 3; } }'

    def integer(number):
        return _constant(number, ValueType.INT)

    expected_expression = _operator(
        ValueType.BOOL,
        5,
        _operator(ValueType.BOOL, 11, _constant(True, ValueType.BOOL)),
        _operator(
            ValueType.BOOL,
            4,
            _operator(
                ValueType.BOOL,
                10,
                _operator(
                    ValueType.INT,
                    5,
                    integer(1),
                    _operator(ValueType.INT, 8, integer(2), integer(3)),
                ),
                integer(8),
            ),
            _operator(ValueType.BOOL, 8, integer(2), integer(3)),
        ),
    )
    expected = Module(
        "Ops",
        triggers=(
            Trigger("T", variables=(Variable(ValueType.BOOL, "result", expected_expression),)),
        ),
    )
    assert parse_module(source) == expected
    assert compile_source(source) == encode_module(expected)
