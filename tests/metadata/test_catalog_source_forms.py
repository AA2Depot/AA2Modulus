"""Source spellings keep independently recorded catalog identities."""

from __future__ import annotations

import json
import re
import struct
import tomllib

import pytest

from aa2modulus.app.compile import CompileError, compile_source
from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.context.operation import SourceContext
from aa2modulus.decompile.format.module import format_module
from aa2modulus.model.records import Expression, Module, NamedConstantRef, Trigger, Variable
from aa2modulus.model.types import EXPR_NAMEDCONSTANT, ValueType
from aa2modulus.semantics.binding.state import SourceBindingError
from aa2modulus.validation.validator.module import validate_module
from tests.support.paths import LANGUAGE_POLICY, REGISTRY
from tests.support.source import parse_module

_TYPE_NAMES = {1: "int", 2: "bool", 3: "float", 4: "string"}


def _policy_and_registry():
    policy = tomllib.loads(LANGUAGE_POLICY.read_text(encoding="utf-8"))
    actions = json.loads((REGISTRY / "actions.json").read_text(encoding="utf-8"))["entries"]
    expressions = json.loads((REGISTRY / "expressions.json").read_text(encoding="utf-8"))["entries"]
    events = json.loads((REGISTRY / "events.json").read_text(encoding="utf-8"))["entries"]
    constants = json.loads((REGISTRY / "named_constants.json").read_text(encoding="utf-8"))[
        "entries"
    ]
    first_constant_by_id = {value_type: {} for value_type in constants}
    for value_type, rows in constants.items():
        for row in rows:
            first_constant_by_id[value_type].setdefault(str(row["id"]), row)
    constants = first_constant_by_id
    return policy, actions, expressions, events, constants


def _literal(type_id: int) -> str:
    return {1: "7", 2: "true", 3: "1.5", 4: '"x"'}[type_id]


def _wire_int_literal(value: int) -> bytes:
    def u32(item: int) -> bytes:
        return struct.pack("<I", item)

    def i32(item: int) -> bytes:
        return struct.pack("<i", item)

    def wstring(item: str) -> bytes:
        encoded = item.encode("utf-16le")
        return u32(len(encoded) // 2) + encoded

    return b"".join(
        (
            wstring("M"),
            wstring(""),
            u32(1),
            wstring("T"),
            u32(0),
            u32(1),
            i32(ValueType.INT),
            wstring("value"),
            i32(ValueType.INT),
            i32(1),
            i32(ValueType.INT),
            i32(value),
            u32(0),
            u32(0),
            u32(0),
        )
    )


def test_all_shipped_literals_compile_to_the_policy_values_and_decompile_as_values():
    policy, *_ = _policy_and_registry()
    assert len(policy["literals"]) == 12
    for spelling, entry in policy["literals"].items():
        source = f'module "M" {{ trigger "T" {{ let value: int = {spelling}; }} }}'
        binary = compile_source(source)
        assert binary == _wire_int_literal(entry["value"])
        module = parse_module(source)
        assert module.triggers[0].variables[0].default_expression.constant.value == entry["value"]
        readable = format_module(module)
        assert f"= {entry['value']};" in readable
        assert spelling not in readable
        assert compile_source(readable) == binary


def test_canonical_names_and_members_bind_to_ids_from_policy_and_registry():
    policy, actions, expressions, events, constants = _policy_and_registry()
    cases: list[tuple[str, str, int, int]] = []

    for identifier, name in policy["preferred_names"]["actions"].items():
        cases.append(("action", name, 0, int(identifier)))
    for identifier, signature in policy["members"]["actions"].items():
        cases.append(("member_action", signature.split("(")[0], 0, int(identifier)))
    for key, signature in policy["members"]["expressions"].items():
        type_name, identifier = key.split(":", 1)
        type_id = {"int": 1, "bool": 2, "float": 3, "string": 4}[type_name]
        cases.append(("member_expression", signature.split("(")[0], type_id, int(identifier)))
    for key, name in policy["preferred_names"]["expressions"].items():
        type_name, identifier = key.split(":", 1)
        type_id = {"int": 1, "bool": 2, "float": 3, "string": 4}[type_name]
        if (type_id, int(identifier)) not in {
            (case[2], case[3]) for case in cases if "expression" in case[0]
        }:
            cases.append(("expression", name, type_id, int(identifier)))
    for identifier, row in events.items():
        cases.append(("event", row["symbol"], 0, int(identifier)))
    for key, name in policy["preferred_names"]["named_constants"].items():
        type_name, identifier = key.split(":", 1)
        type_id = {"int": 1, "bool": 2, "float": 3, "string": 4}[type_name]
        cases.append(("constant", name, type_id, int(identifier)))

    sources: list[str] = []
    for index, (kind, name, type_id, identifier) in enumerate(cases):
        if kind == "event":
            body = f"on {name};"
        elif kind in {"action", "member_action"}:
            signature = actions[str(identifier)]["parameter_types"]
            if kind == "member_action":
                signature = signature[1:]
            args = ", ".join(_literal(item) for item in signature)
            call = f"{name}({args})" if kind == "action" else f"ThisCard.{name}({args})"
            body = call + ";"
        elif kind in {"expression", "member_expression"}:
            row = expressions[_TYPE_NAMES[type_id]][str(identifier)]
            signature = row["parameter_types"]
            if kind == "member_expression":
                signature = signature[1:]
            args = ", ".join(_literal(item) for item in signature)
            if kind == "member_expression":
                call = f"ThisCard.{name}" + (f"({args})" if args else "")
            elif name in {"ThisCard", "ToInt", "ToFloat", "ToString"} and not args:
                call = name
            else:
                call = f"{name}({args})"
            body = f"let value_{index}: {_TYPE_NAMES[type_id]} = {call};"
        else:
            assert str(identifier) in constants[_TYPE_NAMES[type_id]]
            body = f"let value_{index}: {_TYPE_NAMES[type_id]} = {name};"
        sources.append(f'trigger "T{index}" {{ {body} }}')
    assert len(sources) == len(cases)

    # Batches cap each AST while keeping metadata/context construction shared.
    context = SourceContext.create()
    for start in range(0, len(sources), 40):
        expected = cases[start : start + 40]
        # INT/100's declaration mismatch and STRING/13's native defect (N6, N12)
        # are diagnosed; their names still bind, encode and format.
        anomaly_codes = {
            (1, 100): "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH",
            (4, 13): "NATIVE_DEFECTIVE_EXPRESSION",
        }
        expected_codes = [
            anomaly_codes[(type_id, identifier)]
            for kind, _, type_id, identifier in expected
            if kind in {"expression", "member_expression"}
            and (type_id, identifier) in anomaly_codes
        ]
        has_native_type_anomaly = bool(expected_codes)
        source = 'module "Catalog" { ' + " ".join(sources[start : start + 40]) + " }"
        source_module = parse_module(source, context=context)
        binary = encode_module(source_module)
        module = decode_module(binary).module
        assert len(module.triggers) == len(expected)
        if has_native_type_anomaly:
            with pytest.raises(CompileError) as failure:
                compile_source(source, context=context)
            assert [item.code for item in failure.value.diagnostics] == expected_codes
        else:
            assert compile_source(source, context=context) == binary
        formatted = format_module(module, context=context)
        if not has_native_type_anomaly:
            assert compile_source(formatted, context=context) == binary
        assert encode_module(parse_module(formatted, context=context)) == binary
        for trigger, (kind, name, type_id, identifier) in zip(
            module.triggers, expected, strict=True
        ):
            single = Module("Catalog", triggers=(trigger,))
            rendered_trigger = format_module(single, context=context)
            assert name in rendered_trigger, (kind, identifier, name)
            if kind == "event":
                assert trigger.events[0].id == identifier
            elif kind in {"action", "member_action"}:
                action = trigger.gui_actions[0].action
                assert action.id == identifier
                if kind == "member_action":
                    receiver = action.parameters[0]
                    assert (receiver.return_type, receiver.id) == (ValueType.INT, 10)
            elif kind in {"expression", "member_expression"}:
                expression = trigger.variables[0].default_expression
                assert (expression.return_type, expression.id) == (type_id, identifier), name
                if kind == "member_expression":
                    receiver = expression.parameters[0]
                    assert (receiver.return_type, receiver.id) == (ValueType.INT, 10)
            else:
                expression = trigger.variables[0].default_expression
                assert expression.named_constant is not None
                assert (expression.named_constant.value_type, expression.named_constant.id) == (
                    type_id,
                    identifier,
                )


def test_tricky_constant_wires_keep_the_reviewed_readable_or_raw_forms():
    expectations = {
        298: "Constants.EventType.PC_RESPONSE",
        352: "Constants.Period.HOMEROOM",
        365: "raw_expression int 3 { named_constant int 365; }",
        353: "raw_expression int 3 { named_constant int 353; }",
        294: "Constants.Opinion.OPINION_82",
    }
    for identifier, spelling in expectations.items():
        value = Expression(
            ValueType.INT,
            EXPR_NAMEDCONSTANT,
            named_constant=NamedConstantRef(ValueType.INT, identifier),
        )
        module = Module(
            "M", triggers=(Trigger("T", variables=(Variable(ValueType.INT, "v", value),)),)
        )
        binary = encode_module(module)
        source = format_module(module)
        if identifier in {365, 353}:
            assert re.search(
                rf"raw_expression int 3 \{{\s+named_constant int {identifier};", source
            )
        else:
            assert spelling in source
        assert encode_module(parse_module(source)) == binary


def test_int100_keeps_its_native_wire_identity_and_strict_diagnostic():
    module = Module(
        "M",
        triggers=(
            Trigger(
                "T",
                variables=(Variable(ValueType.INT, "v", Expression(ValueType.INT, 100)),),
            ),
        ),
    )
    binary = encode_module(module)
    source = format_module(module)
    assert "Context.NpcOriginalResponse" in source
    assert encode_module(parse_module(source)) == binary
    diagnostics = {item.code for item in validate_module(module, profile="strict").errors}
    assert "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH" in diagnostics


@pytest.mark.parametrize(
    ("call", "result", "identifier"),
    [
        ("ToInt(3.5)", "int", 23),
        ('ToInt("3")', "int", 44),
        ("ToFloat(3)", "float", 9),
        ('ToFloat("3")', "float", 11),
        ("ToString(3)", "string", 9),
        ("ToString(3.5)", "string", 10),
        ("ToString(true)", "string", 11),
    ],
)
def test_conversion_names_select_the_native_overload_from_the_argument_type(
    call, result, identifier
):
    source = f'module "M" {{ trigger "T" {{ let value: {result} = {call}; }} }}'
    expression = parse_module(source).triggers[0].variables[0].default_expression
    assert (expression.return_type, expression.id) == (ValueType[result.upper()], identifier)
    recovered = format_module(decode_module(compile_source(source)).module)
    assert call in recovered
    assert compile_source(recovered) == compile_source(source)


def test_conversion_without_a_matching_overload_is_a_type_mismatch():
    with pytest.raises(SourceBindingError) as raised:
        parse_module('module "M" { trigger "T" { let value: int = ToInt(true); } }')
    assert raised.value.diagnostic.code == "SOURCE_TYPE_MISMATCH"
