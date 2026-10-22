"""Small synthetic inputs for semantic, projection and command regressions.

These models replace temporary audit inputs. They are deliberately constructed
test cases; original native byte inputs stay in fixtures/modules.
"""

from __future__ import annotations

from aa2modulus.model.records import (
    ActionCall,
    Expression,
    GlobalVariable,
    GuiAction,
    Module,
    Trigger,
    Variable,
)
from aa2modulus.model.types import ValueType
from aa2modulus.model.values import Value


def _constant(value: Value) -> Expression:
    return Expression(value.type, 1, constant=value)


def _reference(name: str, kind: ValueType = ValueType.INT) -> Expression:
    return Expression(kind, 2, variable_name=name)


def undefined_variables_module() -> Module:
    """Two unresolved references inside a legal integer For Loop."""

    return Module(
        "Undefined variables",
        triggers=(
            Trigger(
                "T",
                variables=(Variable(ValueType.INT, "counter", _constant(Value.integer(0))),),
                gui_actions=(
                    GuiAction(
                        ActionCall(
                            9,
                            (
                                _reference("counter"),
                                _constant(Value.integer(0)),
                                _constant(Value.integer(1)),
                            ),
                        ),
                        tuple(
                            GuiAction(
                                ActionCall(
                                    110, (_constant(Value.string(key)), _reference("missing"))
                                )
                            )
                            for key in ("first", "second")
                        ),
                    ),
                ),
            ),
        ),
    )


def card_provider_module() -> Module:
    value = Value.integer(3)
    return Module("Provider", globals=(GlobalVariable(ValueType.INT, "external", value, value),))


def card_receiver_module() -> Module:
    return Module(
        "Receiver",
        triggers=(
            Trigger("T", variables=(Variable(ValueType.INT, "copy", _reference("external")),)),
        ),
    )


def type_mismatch_module() -> Module:
    """An INT assignment through an INT reference to a FLOAT local declaration."""

    return Module(
        "Type mismatch",
        triggers=(
            Trigger(
                "T",
                variables=(Variable(ValueType.FLOAT, "weight", _constant(Value.floating(0.0))),),
                gui_actions=(
                    GuiAction(ActionCall(1, (_reference("weight"), _constant(Value.integer(1))))),
                ),
            ),
        ),
    )


def discarded_control_module() -> Module:
    """Conditional children lose enclosing loop state before name resolution."""

    return Module(
        "Discarded control",
        triggers=(
            Trigger(
                "T",
                gui_actions=(
                    GuiAction(
                        ActionCall(6),
                        (
                            GuiAction(
                                ActionCall(2, (_constant(Value.boolean(True)),)),
                                (
                                    GuiAction(
                                        ActionCall(8, (_reference("missing", ValueType.BOOL),))
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
