"""Raw wire identity for unknown records and invalid type scopes."""

from __future__ import annotations

from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.validation.validator.module import validate_module
from tests.support.source import parse_module


def test_unknown_raw_source_round_trips_through_hand_written_bytes():
    source = (
        'module "M" { trigger "T" { '
        "raw_action 9001(raw_expression int 9002 { parameters [ ]; }); } }"
    )
    expected = bytes.fromhex(
        "01000000 4d00 00000000 01000000 "
        "01000000 5400 00000000 00000000 01000000 "
        "29230000 01000000 01000000 2a230000 00000000 "
        "00000000 00000000 00000000"
    )
    parsed = parse_module(source)
    data = encode_module(parsed)
    decoded = decode_module(data, reject_trailing=True).module
    action = decoded.triggers[0].gui_actions[0].action

    assert data == expected
    assert (action.id, action.parameters[0].id) == (9001, 9002)
    assert encode_module(decoded) == expected
    for profile in ("strict", "native"):
        codes = {item.code for item in validate_module(decoded, profile=profile).errors}
        assert {"UNKNOWN_ACTION", "UNKNOWN_EXPRESSION"} <= codes


def test_invalid_wire_type_scope_remains_structurally_writable():
    source = """module "M" { trigger "T" {
      raw_action 9001(raw_expression type 77 9002 { parameters [ ]; });
    } }"""
    parsed = parse_module(source, filename="raw.aa2m")
    data = encode_module(parsed)
    recovered = decode_module(data, reject_trailing=True).module
    expression = recovered.triggers[0].gui_actions[0].action.parameters[0]
    assert (
        recovered.triggers[0].gui_actions[0].action.id,
        expression.return_type,
        expression.id,
    ) == (9001, 77, 9002)
    assert encode_module(recovered) == data
    for profile in ("strict", "native"):
        codes = {
            item.code
            for item in validate_module(recovered, filename="raw.aa2m", profile=profile).errors
        }
        assert "INVALID_EXPRESSION_RETURN_TYPE" in codes
