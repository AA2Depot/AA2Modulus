"""Source spellings keep independently recorded catalog identities."""

from __future__ import annotations

import functools
import json
import re
import struct
import tomllib
from typing import Any

import pytest

from aa2modulus.app.compile import CompileError, compile_source
from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.decompile.format.module import format_module
from aa2modulus.model.records import Expression, Module, NamedConstantRef, Trigger, Variable
from aa2modulus.model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, ValueType
from aa2modulus.semantics.binding.state import SourceBindingError
from aa2modulus.validation.validator.module import validate_module
from tests.support.paths import LANGUAGE_POLICY, REGISTRY
from tests.support.source import parse_module
from tests.support.wire import pack_expression, pack_string, pack_vector

_TYPE_IDS = {"int": 1, "bool": 2, "float": 3, "string": 4}
_TYPE_NAMES = {identifier: name for name, identifier in _TYPE_IDS.items()}
_KINDS = ("action", "member_action", "expression", "member_expression", "event", "constant")
_BATCH = 40  # triggers per module, to keep each syntax tree small

# Natively diagnosed expressions: INT/100 declares bool (N6) and STRING/13 reads
# its first parameter as a string (N12). Their names still bind, encode and
# format, but the compile path rejects them.
_DIAGNOSED = frozenset({(ValueType.INT, 100), (ValueType.STRING, 13)})


@functools.cache
def _read_registry(filename: str) -> dict[str, Any]:
    return json.loads((REGISTRY / filename).read_text(encoding="utf-8"))["entries"]


@functools.cache
def _read_policy() -> dict[str, Any]:
    return tomllib.loads(LANGUAGE_POLICY.read_text(encoding="utf-8"))


def _literal(type_id: int) -> str:
    return {1: "7", 2: "true", 3: "1.5", 4: '"x"'}[type_id]


def _catalog_cases() -> dict[str, list[tuple[str, int, int]]]:
    """Every policy-named target as (spelling, value type id, native id), by kind."""

    policy = _read_policy()

    def typed(key: str) -> tuple[int, int]:
        type_name, identifier = key.split(":", 1)
        return _TYPE_IDS[type_name], int(identifier)

    cases: dict[str, list[tuple[str, int, int]]] = {kind: [] for kind in _KINDS}
    for identifier, name in policy["preferred_names"]["actions"].items():
        cases["action"].append((name, 0, int(identifier)))
    for identifier, signature in policy["members"]["actions"].items():
        cases["member_action"].append((signature.split("(")[0], 0, int(identifier)))
    for key, signature in policy["members"]["expressions"].items():
        cases["member_expression"].append((signature.split("(")[0], *typed(key)))
    members = {(type_id, identifier) for _, type_id, identifier in cases["member_expression"]}
    for key, name in policy["preferred_names"]["expressions"].items():
        if typed(key) not in members:
            cases["expression"].append((name, *typed(key)))
    for identifier, row in _read_registry("events.json").items():
        cases["event"].append((row["symbol"], 0, int(identifier)))
    for key, name in policy["preferred_names"]["named_constants"].items():
        cases["constant"].append((name, *typed(key)))
    return cases


@pytest.fixture(scope="module")
def catalog_cases() -> dict[str, list[tuple[str, int, int]]]:
    return _catalog_cases()


def _statement(kind: str, name: str, type_id: int, identifier: int, index: int) -> str:
    if kind == "event":
        return f"on {name};"
    if kind in {"action", "member_action"}:
        types = _read_registry("actions.json")[str(identifier)]["parameter_types"]
        if kind == "member_action":
            types = types[1:]
        args = ", ".join(_literal(item) for item in types)
        return (f"{name}({args})" if kind == "action" else f"ThisCard.{name}({args})") + ";"
    declaration = f"let value_{index}: {_TYPE_NAMES[type_id]} = "
    if kind == "constant":
        return f"{declaration}{name};"
    types = _read_registry("expressions.json")[_TYPE_NAMES[type_id]][str(identifier)][
        "parameter_types"
    ]
    if kind == "member_expression":
        args = ", ".join(_literal(item) for item in types[1:])
        return f"{declaration}ThisCard.{name}" + (f"({args});" if args else ";")
    args = ", ".join(_literal(item) for item in types)
    if name in {"ThisCard", "ToInt", "ToFloat", "ToString"} and not args:
        return f"{declaration}{name};"
    return f"{declaration}{name}({args});"


def _trigger_texts(formatted: str) -> dict[str, str]:
    """The formatted text of each trigger, by trigger name."""

    parts = re.split(r'(?m)^ *trigger "([^"]+)" \{$', formatted)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


@pytest.mark.parametrize("kind", _KINDS)
def test_canonical_spellings_bind_to_their_ids_and_survive_recovery(kind, catalog_cases, context):
    cases = [
        case
        for case in catalog_cases[kind]
        if kind not in {"expression", "member_expression"} or case[1:] not in _DIAGNOSED
    ]
    assert cases
    for start in range(0, len(cases), _BATCH):
        batch = cases[start : start + _BATCH]
        triggers = " ".join(
            f'trigger "T{index}" {{ {_statement(kind, *case, index)} }}'
            for index, case in enumerate(batch)
        )
        source = f'module "Catalog" {{ {triggers} }}'
        binary = compile_source(source, context=context)
        module = decode_module(binary, reject_trailing=True).module
        assert len(module.triggers) == len(batch)
        formatted = format_module(module, context=context)
        assert compile_source(formatted, context=context) == binary
        texts = _trigger_texts(formatted)
        for index, (name, type_id, identifier) in enumerate(batch):
            trigger = module.triggers[index]
            assert name in texts[f"T{index}"], (kind, identifier, name)
            if kind == "event":
                assert trigger.events[0].id == identifier, name
            elif kind in {"action", "member_action"}:
                action = trigger.gui_actions[0].action
                assert action.id == identifier, name
                if kind == "member_action":
                    receiver = action.parameters[0]
                    assert (receiver.return_type, receiver.id) == (ValueType.INT, 10), name
            else:
                expression = trigger.variables[0].default_expression
                if kind == "constant":
                    assert expression.named_constant is not None, name
                    assert (
                        expression.named_constant.value_type,
                        expression.named_constant.id,
                    ) == (type_id, identifier), name
                else:
                    assert (expression.return_type, expression.id) == (type_id, identifier), name
                if kind == "member_expression":
                    receiver = expression.parameters[0]
                    assert (receiver.return_type, receiver.id) == (ValueType.INT, 10), name


@pytest.mark.parametrize(
    ("declaration", "name", "type_id", "identifier", "code"),
    [
        (
            "let value: int = Context.NpcOriginalResponse;",
            "Context.NpcOriginalResponse",
            ValueType.INT,
            100,
            "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH",
        ),
        (
            'let value: string = Text.Replace(7, 7, 7, "x");',
            "Text.Replace",
            ValueType.STRING,
            13,
            "NATIVE_DEFECTIVE_EXPRESSION",
        ),
    ],
)
def test_natively_diagnosed_names_still_bind_encode_and_format(
    declaration, name, type_id, identifier, code, context
):
    source = f'module "M" {{ trigger "T" {{ {declaration} }} }}'
    with pytest.raises(CompileError) as failure:
        compile_source(source, context=context)
    assert [item.code for item in failure.value.diagnostics] == [code]

    binary = encode_module(parse_module(source, context=context))
    module = decode_module(binary, reject_trailing=True).module
    expression = module.triggers[0].variables[0].default_expression
    assert (expression.return_type, expression.id) == (type_id, identifier)
    formatted = format_module(module, context=context)
    assert name in formatted
    assert encode_module(parse_module(formatted, context=context)) == binary


def test_int100_mismatch_is_a_strict_error_in_a_module_built_without_locations():
    module = Module(
        "M",
        triggers=(
            Trigger("T", variables=(Variable(ValueType.INT, "v", Expression(ValueType.INT, 100)),)),
        ),
    )
    (mismatch,) = validate_module(module, profile="strict").errors
    assert mismatch.code == "EXPRESSION_METADATA_RETURN_TYPE_MISMATCH"
    assert (mismatch.line, mismatch.column, mismatch.offset) == (1, 1, None)


def test_all_shipped_literals_compile_to_the_policy_values_and_decompile_as_values(context):
    entries = _read_policy()["literals"]
    literals = [(spelling, entry["value"]) for spelling, entry in entries.items()]
    assert literals
    triggers = " ".join(
        f'trigger "L{index}" {{ let value: int = {spelling}; }}'
        for index, (spelling, _) in enumerate(literals)
    )
    binary = compile_source(f'module "M" {{ {triggers} }}', context=context)

    def local_value(value: int) -> bytes:
        constant = struct.pack("<ii", ValueType.INT, value)
        return (
            struct.pack("<i", ValueType.INT)
            + pack_string("value")
            + pack_expression(ValueType.INT, EXPR_CONSTANT, constant)
        )

    assert binary == (
        pack_string("M")
        + pack_string("")
        + pack_vector(
            *(
                pack_string(f"L{index}")
                + pack_vector()
                + pack_vector(local_value(value))
                + pack_vector()
                for index, (_, value) in enumerate(literals)
            )
        )
        + pack_vector()
        + pack_vector()
    )
    readable = format_module(decode_module(binary).module, context=context)
    texts = _trigger_texts(readable)
    for index, (spelling, value) in enumerate(literals):
        assert f"= {value};" in texts[f"L{index}"], spelling
        assert spelling not in texts[f"L{index}"]
    assert compile_source(readable, context=context) == binary


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        (298, r"Constants\.EventType\.PC_RESPONSE"),
        (352, r"Constants\.Period\.HOMEROOM"),
        (365, r"raw_expression int 3 \{\s+named_constant int 365;"),
        (353, r"raw_expression int 3 \{\s+named_constant int 353;"),
        (294, r"Constants\.Opinion\.OPINION_82"),
    ],
)
def test_tricky_constant_wires_keep_the_reviewed_readable_or_raw_forms(
    identifier, expected, context
):
    value = Expression(
        ValueType.INT,
        EXPR_NAMEDCONSTANT,
        named_constant=NamedConstantRef(ValueType.INT, identifier),
    )
    module = Module("M", triggers=(Trigger("T", variables=(Variable(ValueType.INT, "v", value),)),))
    source = format_module(module, context=context)
    assert re.search(expected, source)
    assert encode_module(parse_module(source, context=context)) == encode_module(module)


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
    call, result, identifier, context
):
    source = f'module "M" {{ trigger "T" {{ let value: {result} = {call}; }} }}'
    binary = compile_source(source, context=context)
    module = decode_module(binary).module
    expression = module.triggers[0].variables[0].default_expression
    assert (expression.return_type, expression.id) == (ValueType[result.upper()], identifier)
    recovered = format_module(module, context=context)
    assert call in recovered
    assert compile_source(recovered, context=context) == binary


def test_conversion_without_a_matching_overload_is_a_type_mismatch(context):
    with pytest.raises(SourceBindingError) as raised:
        parse_module(
            'module "M" { trigger "T" { let value: int = ToInt(true); } }', context=context
        )
    assert raised.value.diagnostic.code == "SOURCE_TYPE_MISMATCH"
