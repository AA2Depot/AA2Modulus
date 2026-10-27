"""Validation findings tied to independently packed native records."""

from __future__ import annotations

import struct

import pytest

from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.decompile.format.module import format_module
from aa2modulus.decompile.format.text import FormatError
from aa2modulus.validation.validator.module import validate_module
from tests.support.wire import pack_expression, pack_string, pack_vector


def _constant(value_type: int, payload: bytes) -> bytes:
    return pack_expression(value_type, 1, struct.pack("<i", value_type) + payload)


def _action(identifier: int, *parameters: bytes) -> bytes:
    return struct.pack("<i", identifier) + pack_vector(*parameters) + pack_vector()


def _module(
    *,
    events: tuple[bytes, ...] = (),
    variables: tuple[bytes, ...] = (),
    actions: tuple[bytes, ...] = (),
) -> bytes:
    trigger = (
        pack_string("T") + pack_vector(*events) + pack_vector(*variables) + pack_vector(*actions)
    )
    return pack_string("M") + pack_string("") + pack_vector(trigger) + pack_vector() + pack_vector()


def _module_with_globals(*globals_: bytes) -> bytes:
    return (
        pack_string("M") + pack_string("") + pack_vector() + pack_vector(*globals_) + pack_vector()
    )


def _global(declared_type: int, name: str, default: bytes, current: bytes) -> bytes:
    return struct.pack("<i", declared_type) + pack_string(name) + default + current + b"\x00"


def test_native_profile_warns_on_float_declaration_and_integer_assignment_wire():
    float_default = _constant(3, struct.pack("<f", 0.0))
    local = struct.pack("<i", 3) + pack_string("x") + float_default
    reference = pack_expression(1, 2, pack_string("x"))
    integer = _constant(1, struct.pack("<i", 1))
    binary = _module(variables=(local,), actions=(_action(1, reference, integer),))
    assert len(binary) == 108
    assert binary[28:32] == bytes.fromhex("03000000")
    assert binary[66:70] == bytes.fromhex("01000000")

    module = decode_module(binary, reject_trailing=True).module
    strict = validate_module(module)
    native = validate_module(module, profile="native")
    declaration = module.triggers[0].variables[0]
    target = module.triggers[0].gui_actions[0].action.parameters[0]
    assert declaration.binary_location.offset == 28
    assert target.binary_location.offset == 66
    assert [(item.code, item.path, item.offset) for item in strict.errors] == [
        (
            "VARIABLE_TYPE_MISMATCH",
            ("module", "triggers", 0, "gui_actions", 0, "action", "parameters", 0, "return_type"),
            66,
        ),
        (
            "ASSIGNMENT_TYPE_MISMATCH",
            ("module", "triggers", 0, "gui_actions", 0, "action", "parameters", 1),
            80,
        ),
    ]
    assert native.errors == ()
    warning_paths = [(item.code, item.path, item.offset) for item in native.warnings]
    assert warning_paths == [
        (
            "VARIABLE_TYPE_MISMATCH",
            ("module", "triggers", 0, "gui_actions", 0, "action", "parameters", 0, "return_type"),
            66,
        ),
        (
            "ASSIGNMENT_DECLARATION_TYPE",
            ("module", "triggers", 0, "gui_actions", 0, "action", "parameters", 1),
            80,
        ),
    ]
    assert encode_module(module) == binary


def test_discarded_break_keeps_its_native_offset_and_profile_diagnostic():
    condition = _constant(2, b"\x01")
    binary = _module(actions=(_action(7, condition),))
    assert len(binary) == 65
    assert binary[32:36] == struct.pack("<i", 7)
    assert binary[40:44] == bytes.fromhex("02000000")
    assert binary[52] == 1
    module = decode_module(binary, reject_trailing=True).module

    strict = validate_module(module)
    native = validate_module(module, profile="native")
    assert strict.is_valid
    (warning,) = native.warnings
    assert warning.code == "NATIVE_DISCARDED_CONTROL"
    assert (warning.offset, warning.path) == (
        32,
        ("module", "triggers", 0, "gui_actions", 0, "action"),
    )
    assert encode_module(module) == binary


def test_native_records_report_unknown_ids_and_wrong_parameter_types_at_wire_locations():
    unknown_event = struct.pack("<i", 999) + pack_vector()
    int_argument = _constant(1, struct.pack("<i", 1))
    wrong_action = _action(2, int_argument)
    unknown_action = _action(999)
    unknown_expression = pack_expression(1, 999, pack_vector())
    local = struct.pack("<i", 1) + pack_string("bad") + unknown_expression
    module = decode_module(
        _module(
            events=(unknown_event,), variables=(local,), actions=(wrong_action, unknown_action)
        ),
        reject_trailing=True,
    ).module

    diagnostics = validate_module(module).errors
    by_code = {item.code: item for item in diagnostics}
    assert {
        code: (by_code[code].path, by_code[code].offset)
        for code in (
            "UNKNOWN_EVENT",
            "UNKNOWN_ACTION",
            "UNKNOWN_EXPRESSION",
            "ACTION_PARAMETER_TYPE",
        )
    } == {
        "UNKNOWN_EVENT": (("module", "triggers", 0, "events", 0, "id"), 24),
        "UNKNOWN_ACTION": (("module", "triggers", 0, "gui_actions", 1, "action", "id"), 94),
        "UNKNOWN_EXPRESSION": (
            ("module", "triggers", 0, "variables", 0, "default_expression", "id"),
            50,
        ),
        "ACTION_PARAMETER_TYPE": (
            ("module", "triggers", 0, "gui_actions", 0, "action", "parameters", 0, "return_type"),
            74,
        ),
    }
    assert encode_module(module) == _module(
        events=(unknown_event,), variables=(local,), actions=(wrong_action, unknown_action)
    )


@pytest.mark.parametrize(
    ("wire", "code", "path", "offset"),
    (
        (
            _module_with_globals(
                _global(1, "x", struct.pack("<iB", 2, 1), struct.pack("<ii", 1, 1))
            ),
            "GLOBAL_DEFAULT_TYPE",
            ("module", "globals", 0, "default_value"),
            28,
        ),
        (
            _module_with_globals(
                _global(1, "x", struct.pack("<ii", 1, 1), struct.pack("<iB", 2, 1))
            ),
            "GLOBAL_CURRENT_TYPE",
            ("module", "globals", 0, "current_value"),
            36,
        ),
        (
            _module_with_globals(_global(77, "x", struct.pack("<i", 0), struct.pack("<i", 0))),
            "INVALID_VARIABLE_TYPE",
            ("module", "globals", 0, "type"),
            18,
        ),
    ),
    ids=("global-default-tag", "global-current-tag", "unrepresentable-declaration"),
)
def test_malformed_global_wire_has_profile_diagnostics_and_cannot_be_formatted(
    wire, code, path, offset
):
    module = decode_module(wire, reject_trailing=True).module
    strict = next(item for item in validate_module(module).errors if item.code == code)
    native_result = validate_module(module, profile="native")
    native = next(item for item in native_result.diagnostics if item.code == code)
    assert (strict.path, strict.offset, strict.severity) == (path, offset, "error")
    assert (native.path, native.offset) == (path, offset)
    assert native.severity == ("error" if code == "INVALID_VARIABLE_TYPE" else "warning")
    with pytest.raises(FormatError):
        format_module(module)
