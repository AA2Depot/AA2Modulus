"""Hand-written wire expectations for the native binary layout."""

from __future__ import annotations

import struct

import pytest

from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import WriteError, WriterLimits, encode_module
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
from aa2modulus.model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, ValueType
from aa2modulus.model.values import Value
from tests.support.wire import pack_expression, pack_string, pack_vector


def pack_value(value_type: int, payload: bytes = b"") -> bytes:
    return struct.pack("<i", value_type) + payload


def pack_global(
    value_type: int, name: str, default: bytes, current: bytes, initialized: int
) -> bytes:
    return (
        struct.pack("<i", value_type) + pack_string(name) + default + current + bytes([initialized])
    )


def pack_module(
    name: str = "", triggers: tuple[bytes, ...] = (), globals_: tuple[bytes, ...] = ()
) -> bytes:
    return (
        pack_string(name)
        + pack_string("")
        + pack_vector(*triggers)
        + pack_vector(*globals_)
        + pack_vector()
    )


def test_empty_module_and_utf16_code_units_have_exact_wire_bytes():
    assert encode_module(Module("")) == b"\x00" * 20
    expected = b"\x05\x00\x00\x00A\x00=\xd8\x00\xde\x00\xd8Z\x00" + b"\x00" * 16
    assert encode_module(Module("A\U0001f600\ud800Z")) == expected
    assert decode_module(expected).module.name == "A\U0001f600\ud800Z"


def test_nested_unknown_records_encode_to_independently_packed_bytes():
    unknown = Expression(77, 9001)
    integer = Expression(ValueType.INT, EXPR_CONSTANT, constant=Value.integer(-7))
    module = Module(
        "U",
        triggers=(
            Trigger(
                "T",
                events=(Event(9002, (unknown,)),),
                gui_actions=(
                    GuiAction(ActionCall(9003, (integer,)), (GuiAction(ActionCall(9004)),)),
                ),
            ),
        ),
    )
    expected = (
        pack_string("U")
        + pack_string("")
        + pack_vector(
            pack_string("T")
            + pack_vector(
                struct.pack("<i", 9002) + pack_vector(pack_expression(77, 9001, pack_vector()))
            )
            + pack_vector()
            + pack_vector(
                struct.pack("<i", 9003)
                + pack_vector(
                    pack_expression(1, EXPR_CONSTANT, pack_value(1, struct.pack("<i", -7)))
                )
                + pack_vector(struct.pack("<i", 9004) + pack_vector() + pack_vector())
            )
        )
        + pack_vector()
        + pack_vector()
    )
    assert encode_module(module) == expected
    decoded = decode_module(expected, reject_trailing=True).module
    assert decoded == module


def test_global_payloads_use_native_widths_and_preserve_float_bits():
    bits = 0x7FC00001
    expected = pack_module(
        globals_=(
            pack_global(
                1,
                "number",
                pack_value(1, struct.pack("<i", -4)),
                pack_value(1, struct.pack("<i", 8)),
                1,
            ),
            pack_global(
                3,
                "float",
                pack_value(3, struct.pack("<I", bits)),
                pack_value(3, struct.pack("<I", bits)),
                0,
            ),
            pack_global(
                4,
                "text",
                pack_value(4, pack_string("hello")),
                pack_value(4, pack_string("world")),
                1,
            ),
        )
    )
    module = decode_module(expected).module
    assert module.globals[0].default_value.value == -4
    assert module.globals[0].current_value.value == 8
    assert module.globals[1].default_value.binary32_bits == bits
    assert module.globals[2].current_value.value == "world"
    assert encode_module(module) == expected


def test_noncanonical_native_boolean_bytes_decode_as_true_and_write_canonically():
    value = pack_value(2, b"\x01")
    canonical = pack_module(
        "Booleans",
        globals_=(pack_global(2, "flag", value, value, 1),),
    )
    data = bytearray(canonical)
    first = data.index(value)
    second = data.index(value, first + len(value))
    data[first + len(value) - 1] = 255
    data[second + len(value) - 1] = 255
    data[second + len(value)] = 255

    decoded = decode_module(data, reject_trailing=True).module
    assert decoded.globals[0].default_value.value is True
    assert decoded.globals[0].current_value.value is True
    assert decoded.globals[0].initialized is True
    assert encode_module(decoded) == canonical


def test_unusual_float32_bits_survive_round_trip():
    for bits in (0x80000000, 0x00000001, 0x7F800000, 0x7FC00001, 0x7FA00001):
        value = Value.floating_bits(bits)
        module = Module("float", globals=(GlobalVariable(ValueType.FLOAT, "x", value, value),))
        value_wire = struct.pack("<iI", ValueType.FLOAT, bits)
        text_wire = pack_string("x")
        expected = (
            pack_string("float")
            + pack_string("")
            + pack_vector()
            + pack_vector(
                struct.pack("<i", ValueType.FLOAT) + text_wire + value_wire + value_wire + b"\x00"
            )
            + pack_vector()
        )
        assert encode_module(module) == expected
        decoded = decode_module(expected).module
        assert decoded.globals[0].default_value.binary32_bits == bits


def test_writer_limits_and_unrepresentable_integer_are_reported():
    with pytest.raises(WriteError, match="length 3"):
        encode_module(Module("abc"), limits=WriterLimits(max_string_code_units=2))
    with pytest.raises(WriteError, match="triggers length 1"):
        encode_module(
            Module("M", triggers=(Trigger("T"),)),
            limits=WriterLimits(max_vector_elements=0),
        )
    with pytest.raises(WriteError, match="output exceeds limit"):
        encode_module(Module(""), limits=WriterLimits(max_output_bytes=19))
    nested = GuiAction(ActionCall(108), (GuiAction(ActionCall(108)),))
    with pytest.raises(WriteError, match="recursion depth"):
        encode_module(
            Module("M", triggers=(Trigger("T", gui_actions=(nested,)),)),
            limits=WriterLimits(max_recursion_depth=0),
        )
    with pytest.raises(WriteError, match="encoded node limit"):
        encode_module(
            Module("M", triggers=(Trigger("T", gui_actions=(nested,)),)),
            limits=WriterLimits(max_encoded_nodes=1),
        )
    wide = Expression(ValueType.INT, EXPR_CONSTANT, constant=Value.integer(2**31))
    with pytest.raises(WriteError, match="int value is outside the int32 range"):
        encode_module(
            Module("M", triggers=(Trigger("T", variables=(Variable(ValueType.INT, "x", wide),)),))
        )


def test_named_constant_reference_scope_is_written_as_the_wire_type():
    expression = Expression(
        ValueType.INT,
        EXPR_NAMEDCONSTANT,
        named_constant=NamedConstantRef(ValueType.INT, 901),
    )
    module = Module(
        "M", triggers=(Trigger("T", variables=(Variable(ValueType.INT, "x", expression),)),)
    )
    expected = (
        pack_string("M")
        + pack_string("")
        + pack_vector(
            pack_string("T")
            + pack_vector()
            + pack_vector(
                struct.pack("<i", 1)
                + pack_string("x")
                + pack_expression(1, EXPR_NAMEDCONSTANT, struct.pack("<i", 901))
            )
            + pack_vector()
        )
        + pack_vector()
        + pack_vector()
    )
    assert encode_module(module) == expected
