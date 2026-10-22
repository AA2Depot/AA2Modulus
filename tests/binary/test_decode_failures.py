"""Malformed, truncated and oversized binaries fail with bounded, located errors."""

from __future__ import annotations

import struct

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from aa2modulus.binary.reader import DecodeError, ReaderLimits, decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.model.records import (
    ActionCall,
    Event,
    Expression,
    GlobalVariable,
    GuiAction,
    Module,
    NamedConstantRef,
    Trigger,
    Variable,
)
from aa2modulus.model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, ValueType
from aa2modulus.model.values import Value

TEXT = st.text(max_size=8)
TYPE = st.sampled_from(
    (ValueType.INVALID, ValueType.INT, ValueType.BOOL, ValueType.FLOAT, ValueType.STRING)
)


@st.composite
def values(draw):
    value_type = draw(TYPE)
    if value_type is ValueType.INVALID:
        return Value.invalid()
    if value_type is ValueType.INT:
        return Value.integer(draw(st.integers(min_value=-(2**31), max_value=2**31 - 1)))
    if value_type is ValueType.BOOL:
        return Value.boolean(draw(st.booleans()))
    if value_type is ValueType.FLOAT:
        return Value.floating(draw(st.floats(width=32, allow_nan=False, allow_infinity=False)))
    return Value.string(draw(TEXT))


@st.composite
def expressions(draw):
    return draw(
        st.recursive(
            st.one_of(
                st.builds(
                    lambda value: Expression(value.type, EXPR_CONSTANT, constant=value),
                    values(),
                ),
                st.builds(
                    lambda value_type, name: Expression(
                        value_type,
                        EXPR_VAR,
                        variable_name=name,
                    ),
                    TYPE,
                    TEXT,
                ),
                st.builds(
                    lambda value_type, identifier: Expression(
                        value_type,
                        EXPR_NAMEDCONSTANT,
                        named_constant=NamedConstantRef(value_type, identifier),
                    ),
                    TYPE,
                    st.integers(min_value=-10, max_value=10),
                ),
            ),
            lambda child: st.builds(
                lambda value_type, identifier, parameters: Expression(
                    value_type,
                    identifier,
                    parameters=parameters,
                ),
                TYPE,
                st.integers(min_value=4, max_value=10_000),
                st.lists(child, max_size=3).map(tuple),
            ),
            max_leaves=5,
        )
    )


@st.composite
def modules(draw):
    expression = expressions()
    variable_type = draw(TYPE)
    default = draw(values())
    current = draw(values())
    global_variable = GlobalVariable(
        variable_type,
        draw(TEXT),
        default,
        current,
        draw(st.booleans()),
    )
    local = Variable(variable_type, draw(TEXT), draw(expression))
    action = GuiAction(
        ActionCall(
            draw(st.integers(min_value=-10, max_value=10_000)),
            draw(st.lists(expression, max_size=3).map(tuple)),
        ),
        draw(
            st.lists(
                st.builds(
                    lambda call: GuiAction(call),
                    st.builds(
                        ActionCall, st.integers(min_value=-10, max_value=10_000), st.just(())
                    ),
                ),
                max_size=2,
            ).map(tuple)
        ),
    )
    trigger = Trigger(
        draw(TEXT),
        events=(
            Event(
                draw(st.integers(min_value=-10, max_value=10_000)),
                draw(st.lists(expression, max_size=3).map(tuple)),
            ),
        ),
        variables=(local,),
        gui_actions=(action,),
    )
    return Module(
        draw(TEXT),
        draw(TEXT),
        triggers=(trigger,),
        globals=(global_variable,),
        dependencies=(draw(TEXT),),
    )


def _string(value: str) -> bytes:
    encoded = value.encode("utf-16-le", errors="surrogatepass")
    return struct.pack("<I", len(encoded) // 2) + encoded


def _empty_module() -> bytes:
    return _string("") + _string("") + struct.pack("<III", 0, 0, 0)


@given(modules())
def test_bounded_model_binary_round_trip(module):
    encoded = encode_module(module)
    decoded = decode_module(encoded, reject_trailing=True).module
    assert decoded == module
    assert decoded.to_ir() == module.to_ir()


@given(st.binary(max_size=19))
def test_inputs_shorter_than_the_minimum_module_layout_are_rejected(data):
    # Even an empty module needs five four-byte string/vector lengths.
    with pytest.raises(DecodeError) as raised:
        decode_module(data)
    assert 0 <= raised.value.offset <= len(data)
    assert raised.value.path[0] == "module"


def test_truncated_input_reports_exact_boundary_and_path():
    with pytest.raises(DecodeError) as raised:
        decode_module(_empty_module()[:-1])
    assert raised.value.offset == 16
    assert raised.value.path == ("module", "dependencies")


def test_trailing_bytes_are_reported_or_rejected():
    data = _empty_module() + b"\xaa\xbb"
    result = decode_module(data)
    assert (result.trailing_bytes.offset, result.trailing_bytes.count) == (20, 2)
    with pytest.raises(DecodeError, match="trailing bytes") as raised:
        decode_module(data, reject_trailing=True)
    assert raised.value.offset == 20


def test_reader_limits_and_unknown_value_types_are_checked_before_allocation():
    with pytest.raises(DecodeError, match="length 3") as string_error:
        decode_module(_string("abc"), limits=ReaderLimits(max_string_code_units=2))
    assert string_error.value.path == ("module", "name")

    too_many_triggers = _string("") + _string("") + struct.pack("<I", 2)
    with pytest.raises(DecodeError, match="vector length 2"):
        decode_module(too_many_triggers, limits=ReaderLimits(max_vector_elements=1))

    with pytest.raises(DecodeError, match="input exceeds limit"):
        decode_module(_empty_module(), limits=ReaderLimits(max_input_bytes=19))

    # Module fields then one global whose default value has unknown type 5.
    bad_value = (
        _string("")
        + _string("")
        + struct.pack("<II", 0, 1)
        + struct.pack("<i", 1)
        + _string("bad")
        + struct.pack("<i", 5)
    )
    with pytest.raises(DecodeError, match="unknown Value type id 5"):
        decode_module(bad_value)


def test_reader_recursion_and_node_limits_stop_nested_decoding():
    child = struct.pack("<i", 2) + struct.pack("<II", 0, 0)
    root = struct.pack("<i", 1) + struct.pack("<I", 0) + struct.pack("<I", 1) + child
    trigger = _string("T") + struct.pack("<II", 0, 0) + struct.pack("<I", 1) + root
    data = _string("") + _string("") + struct.pack("<I", 1) + trigger + struct.pack("<II", 0, 0)
    with pytest.raises(DecodeError, match="recursion depth"):
        decode_module(data, limits=ReaderLimits(max_recursion_depth=1))
    with pytest.raises(DecodeError, match="decoded node limit"):
        decode_module(data, limits=ReaderLimits(max_decoded_nodes=1))


def _mutation_seed(name: str, number: int) -> tuple[bytes, dict[str, int]]:
    """Build native field order independently of the production writer."""

    data = bytearray()
    offsets = {}

    def integer(value: int, *, signed: bool = False) -> int:
        offset = len(data)
        data.extend(struct.pack("<i" if signed else "<I", value))
        return offset

    def string(value: str) -> int:
        raw = value.encode("utf-16-le")
        offset = integer(len(raw) // 2)
        data.extend(raw)
        return offset

    offsets["name-length"] = string(name)
    string("")  # module description
    integer(1)  # triggers
    string("T")
    integer(0)  # events
    integer(0)  # locals
    integer(1)  # GUI actions
    integer(9000, signed=True)
    offsets["parameter-count"] = integer(1)
    integer(1, signed=True)  # expression return scope: int
    integer(EXPR_CONSTANT, signed=True)
    offsets["value-type"] = integer(ValueType.INT, signed=True)
    integer(number, signed=True)
    integer(0)  # GUI action children
    integer(0)  # globals
    integer(1)  # dependencies
    offsets["dependency-length"] = string("tail")
    return bytes(data), offsets


@pytest.mark.parametrize(
    "kind",
    ("name-length", "parameter-count", "value-type", "dependency-length", "truncation", "trailing"),
)
@settings(max_examples=20, deadline=None)
@given(
    name=st.text(alphabet="abc", max_size=8),
    number=st.integers(min_value=-100, max_value=100),
    choice=st.integers(min_value=0, max_value=2**16),
)
@example(name="", number=0, choice=0)
def test_structured_binary_mutations_report_bounded_errors(kind, name, number, choice):
    data, offsets = _mutation_seed(name, number)
    original = decode_module(data, reject_trailing=True).module
    assert original.name == name
    assert original.triggers[0].gui_actions[0].action.parameters[0].constant == Value.integer(
        number
    )
    limits = ReaderLimits(
        max_input_bytes=256,
        max_string_code_units=16,
        max_vector_elements=8,
        max_decoded_nodes=16,
        max_recursion_depth=8,
    )
    if kind == "truncation":
        # All cuts are >= the 20-byte minimum and strictly inside a valid body.
        cut = 20 + choice % (len(data) - 20)
        mutated = data[:cut]
        expected_offset = None
        expected_path = None
        message = ""
    elif kind == "trailing":
        mutated = data + bytes([choice % 256])
        expected_offset, expected_path = len(data), ()
        message = "trailing bytes"
    else:
        offset = offsets[kind]
        mutated = bytearray(data)
        replacement = 77 if kind == "value-type" else 2**32 - 1 - choice
        struct.pack_into("<I", mutated, offset, replacement)
        expected_offset = offset
        expected_path = {
            "name-length": ("module", "name"),
            "parameter-count": ("module", "triggers", 0, "gui_actions", 0, "action", "parameters"),
            "value-type": (
                "module",
                "triggers",
                0,
                "gui_actions",
                0,
                "action",
                "parameters",
                0,
                "constant",
            ),
            "dependency-length": ("module", "dependencies", 0),
        }[kind]
        message = "unknown Value type id" if kind == "value-type" else "exceeds limit"
    with pytest.raises(DecodeError) as raised:
        decode_module(mutated, limits=limits, reject_trailing=True)
    assert 0 <= raised.value.offset <= len(mutated)
    if expected_offset is not None:
        assert raised.value.offset == expected_offset
        assert raised.value.path == expected_path
        assert message in raised.value.message
    else:
        assert raised.value.path[0] == "module"
        assert "input" in raised.value.message or "truncated" in raised.value.message
