"""Native fixture hashes and end-to-end source recovery."""

from __future__ import annotations

import hashlib

from aa2modulus.app.compile import compile_module, compile_source
from aa2modulus.app.decompile import decompile_module
from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.decompile.format.module import format_module
from aa2modulus.validation.validator.module import validate_module
from tests.support.fixture_data import FIXTURE_HASHES
from tests.support.paths import MODULE_FIXTURES
from tests.support.source import parse_module

RACE_HUMAN_SOURCE = """module "Race-Human" {
  description "Is a human";
  trigger "Init" {
    on CARD_ADDED;
    let race: string = "Human ";
    if TriggeringCard == ThisCard {
      ThisCard.SetString("Race", race + ThisCard.GetString("Race", ""));
    }
  }
}"""


def test_native_fixtures_decompile_and_recompile_byte_identically(metadata, module_fixture):
    name, data = module_fixture
    assert hashlib.sha256(data).hexdigest() == FIXTURE_HASHES[name]
    decoded = decode_module(data, reject_trailing=True).module
    assert encode_module(decoded) == data
    validation = validate_module(decoded, metadata=metadata, filename=name)
    assert validation.errors == ()
    assert validation.warnings == ()
    assert compile_module(decoded, filename=name, metadata=metadata) == data

    result = decompile_module(data, metadata=metadata, filename=name, reject_trailing=True)
    parsed = parse_module(result.source, filename=f"{name}.aa2m", metadata=metadata)
    assert parsed.to_ir() == decoded.to_ir()
    assert compile_source(result.source, filename=f"{name}.aa2m", metadata=metadata) == data
    assert format_module(parsed, metadata=metadata) == result.source


def test_hand_authored_race_human_source_matches_native_bytes(metadata):
    data = (MODULE_FIXTURES / "Race-Human").read_bytes()
    assert compile_source(RACE_HUMAN_SOURCE, filename="Race-Human.aa2m", metadata=metadata) == data

    module = decode_module(data, reject_trailing=True).module
    trigger = module.triggers[0]
    assert (module.name, module.description) == ("Race-Human", "Is a human")
    assert (trigger.name, tuple(event.id for event in trigger.events)) == ("Init", (6,))
    assert (trigger.variables[0].name, trigger.variables[0].default_expression.constant.value) == (
        "race",
        "Human ",
    )
    (conditional,) = trigger.gui_actions
    assert conditional.action.id == 2
    (comparison,) = conditional.action.parameters
    assert (comparison.return_type, comparison.id) == (2, 8)
    assert tuple(parameter.id for parameter in comparison.parameters) == (9, 10)
    assignment = conditional.children[0].action
    receiver, key, concatenation = assignment.parameters
    assert assignment.id == 26
    assert (receiver.return_type, receiver.id) == (1, 10)
    assert key.constant.value == "Race"
    assert (concatenation.return_type, concatenation.id) == (4, 8)
    assert tuple(parameter.id for parameter in concatenation.parameters) == (2, 7)
    assert concatenation.parameters[0].variable_name == "race"
    assert concatenation.parameters[1].parameters[-1].constant.value == ""
    assert module.globals == ()
    assert module.dependencies == ()
