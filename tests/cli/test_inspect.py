"""User-visible inspection output and its exit behavior."""

from __future__ import annotations

from aa2modulus.binary.writer import encode_module
from aa2modulus.model.records import (
    ActionCall,
    Event,
    Expression,
    GuiAction,
    Module,
    NamedConstantRef,
    Trigger,
    Variable,
)
from aa2modulus.model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, ValueType
from aa2modulus.model.values import Value
from tests.support.cli import invoke_cli
from tests.support.paths import MODULE_FIXTURES


def test_inspect_renders_native_fixture_tree(capsys):
    result = invoke_cli(capsys, "inspect", str(MODULE_FIXTURES / "Race-Human"))
    assert result.returncode == 0, result.stderr
    assert "Module: Race-Human" in result.stdout
    assert "Card Added to Class [event id=6]" in result.stdout
    assert "If (TriggerCard == ThisCard) then [action id=2]" in result.stdout
    assert "type=string, id=1" in result.stdout
    assert result.stderr == ""


def test_inspect_renders_known_expression_precedence_and_conditions(tmp_path, capsys):
    def variable(name):
        return Expression(ValueType.INT, EXPR_VAR, variable_name=name)

    def add(left, right):
        return Expression(ValueType.INT, 5, parameters=(left, right))

    def multiply(left, right):
        return Expression(ValueType.INT, 8, parameters=(left, right))

    condition = Expression(
        ValueType.BOOL,
        8,
        parameters=(variable("left"), variable("right")),
    )
    module = Module(
        "Inspection",
        triggers=(
            Trigger(
                "Init",
                events=(Event(6),),
                gui_actions=(
                    GuiAction(
                        ActionCall(
                            999, (multiply(add(variable("a"), variable("b")), variable("c")),)
                        )
                    ),
                    GuiAction(ActionCall(2, (condition,))),
                ),
            ),
            Trigger("Idle"),
        ),
    )
    path = tmp_path / "inspection"
    path.write_bytes(encode_module(module))

    result = invoke_cli(capsys, "inspect", str(path))

    assert result.returncode == 0, result.stderr
    assert "(var(a) + var(b)) * var(c) [type=int, id=8]" in result.stdout
    assert "If (var(left) == var(right)) then [action id=2]" in result.stdout
    assert (
        "[2] Trigger: Idle\n  Events:\n    (none)\n  Local variables:\n    (none)\n"
        "  Actions:\n    (none)\n"
    ) in result.stdout


def test_inspect_shows_unknown_records_malformed_expressions_and_trailing_bytes(tmp_path, capsys):
    unknown_expression = Expression(
        77,
        901,
        parameters=(Expression(ValueType.INT, EXPR_VAR, variable_name="points"),),
    )
    module = Module(
        "Inspect",
        dependencies=("Dependency",),
        triggers=(
            Trigger(
                "Init",
                variables=(
                    # Known named constants and variables are rendered by the shipped registry.
                    Variable(
                        ValueType.INT,
                        "kind",
                        Expression(
                            ValueType.INT,
                            EXPR_NAMEDCONSTANT,
                            named_constant=NamedConstantRef(ValueType.INT, 1),
                        ),
                    ),
                ),
                gui_actions=(
                    GuiAction(
                        ActionCall(
                            999,
                            (
                                Expression(ValueType.INT, EXPR_CONSTANT, constant=Value.integer(3)),
                                Expression(
                                    ValueType.INT,
                                    5,
                                    parameters=(
                                        Expression(ValueType.INT, EXPR_VAR, variable_name="x"),
                                    ),
                                ),
                                unknown_expression,
                                Expression(
                                    ValueType.INT,
                                    EXPR_NAMEDCONSTANT,
                                    named_constant=NamedConstantRef(ValueType.INT, 999),
                                ),
                            ),
                        ),
                        children=(GuiAction(ActionCall(999)),),
                    ),
                ),
            ),
        ),
    )
    path = tmp_path / "unknown"
    native_bytes = encode_module(module)
    path.write_bytes(native_bytes + b"\xaa\xbb")
    clean_path = tmp_path / "unknown-clean"
    clean_path.write_bytes(native_bytes)

    result = invoke_cli(capsys, "inspect", str(path))
    strict = invoke_cli(capsys, "inspect", "--strict", str(path))
    strict_records = invoke_cli(capsys, "inspect", "--strict", str(clean_path))

    assert result.returncode == 0, result.stderr
    assert "Dependencies:\n  - Dependency" in result.stdout
    assert "default=LOVE [type=int, id=3]" in result.stdout
    assert "UNKNOWN_ACTION(id=999)" in result.stdout
    assert "UNKNOWN_NAMED_CONSTANT(type=int, id=999)" in result.stdout
    assert "UNKNOWN_EXPRESSION(" in result.stdout and "id=901" in result.stdout
    assert "error[EXPRESSION_ARITY]:" in result.stdout
    assert "var(x) + %p" in result.stdout
    assert "Warning: 2 trailing bytes remain" in result.stdout
    assert strict.returncode == 1
    assert "trailing bytes" in strict.stderr
    assert strict_records.returncode == 1
    assert "error[UNKNOWN_ACTION]:" in strict_records.stdout


def test_inspect_rejects_malformed_and_missing_inputs_with_distinct_exits(tmp_path, capsys):
    malformed = tmp_path / "truncated"
    malformed.write_bytes((MODULE_FIXTURES / "Race-Human").read_bytes()[:-1])
    invalid = invoke_cli(capsys, "inspect", str(malformed))
    missing = invoke_cli(capsys, "inspect", str(tmp_path / "missing"))
    no_command = invoke_cli(capsys)

    assert invalid.returncode == 1 and "invalid module" in invalid.stderr
    assert missing.returncode == 2 and "does not exist" in missing.stderr
    assert no_command.returncode == 2 and "usage:" in no_command.stderr.lower()
