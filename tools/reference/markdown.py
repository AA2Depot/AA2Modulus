"""reference.md: the human-readable form of reference.json"""

from __future__ import annotations

import json
from typing import Any

from aa2modulus.model.types import ValueType

SECTIONS = (
    ("Actions", "actions"),
    ("Events", "events"),
    ("Expressions", "expressions"),
    ("Named constants", "named_constants"),
)

HEADER = """\
# Native Metadata Reference

Generated from the committed metadata snapshot and source policy. `reference.json` is \
the lossless machine-readable form. Stable named-constant anchors use scope and original \
record ordinal, so duplicate IDs and names remain distinct.
A source spelling marked with multiple candidates has more than one target under the \
policy. Expression calls can still resolve through parameter and expected return types; \
unresolved collisions are diagnosed as ambiguous.

Source revision: `{revision}`.
Catalog fingerprint: `{fingerprint}`.
Binding, formatting and editor queries share these catalog forms. Readability is separate \
from native initialization, callback context safety and native re-save stability; \
reviewed defects remain diagnosed independently.

## Contents

- [Actions](#actions)
- [Events](#events)
- [Expressions](#expressions)
- [Named constants](#named-constants)
- [Literal source values](#literal-source-values)
- [Operators](#operator-bindings)
"""

SOURCE_VALUES = """\
## Literal Source Values

These qualified source names lower to primitive literals backed by verified native rows. \
They are distinct from native named references; recovery keeps ordinary literals numeric \
and preserves existing native wire IDs.

| Source name | Type | Literal | Native evidence row |
| --- | --- | --- | --- |"""

OPERATORS = """
## Operator Bindings

| Token | Precedence | Fixity | Associativity | Signature | Expression ID | Short circuit |
| --- | ---: | --- | --- | --- | ---: | --- |"""


def render(data: dict[str, Any]) -> str:
    provenance = data["provenance"]
    rows = [
        HEADER.format(
            revision=provenance["source_revision"], fingerprint=provenance["catalog_fingerprint"]
        )
    ]

    for title, key in SECTIONS:
        rows += [f"## {title}", ""]
        if key == "named_constants":
            rows += [
                "Records remain in registry order within each type scope. Duplicate IDs are "
                "preserved.",
                "",
            ]
        for item in data[key]:
            rows += _entry(item, key)

    rows.append(SOURCE_VALUES)
    for value in data["source_values"]:
        type_name = ValueType(value["value"]["type"]).name.lower()
        key = value["documentation_key"]
        rows.append(
            f"| `{value['name']}` | `{type_name}` | `{_value(value['value'])}` | [{key}](#{key}) |"
        )

    rows.append(OPERATORS)
    for operator in data["operators"]:
        parameters = ", ".join(item["name"] for item in operator["parameter_types"])
        signature = f"{operator['return_type']['name']}({parameters})"
        token = operator["token"].replace("|", r"\|")
        rows.append(
            f"| `{token}` | {operator['precedence']} | {operator['fixity']} | "
            f"{operator['associativity']} | `{signature}` | {operator['expression_id']} | "
            f"{str(operator['short_circuit']).lower()} |"
        )

    # A line ending in a Markdown hard break is followed by a blank line.
    lines = []
    for row in rows:
        for line in row.split("\n"):
            lines.append(line.rstrip())
            if line.endswith("  "):
                lines.append("")

    return "\n".join(lines) + "\n"


def _entry(item: dict[str, Any], key: str) -> list[str]:
    names = item["source_names"]
    candidates = names["candidates"]
    preferred = names["preferred"]
    name = preferred if preferred in candidates else next(iter(candidates), None)
    member = next(
        (
            form
            for form in item.get("receiver_forms", ())
            if name == f"<{form['receiver']['role']}>.{form['member']}"
        ),
        None,
    )
    catalog = item.get("catalog", {})

    scope = item["scope"]["name"] + " / " if item.get("scope") else ""
    title = member["member"] if member else name or item["name"]
    spellings = ", ".join(f"`{spelling}`" for spelling in candidates)
    flags = _flags(item)

    rows = [
        f'<a id="{item["anchor"]}"></a>',
        f"### {scope}{title} — ID `{item['id']}`",
        "",
        f"**Signature:** {_signature(item, key, name, member)}",
        "",
        f"**Native name:** `{item['name']}`  ",
        f"**Native GUI label (provenance):** {item['interactive_name'] or '—'}  ",
        f"**Category:** {item.get('category') or '—'}  ",
        f"**Candidate source spellings:** {spellings or 'none'}  ",
        f"**Status:** {', '.join(flags) if flags else 'ordinary'}",
        "",
    ]

    if item.get("implementation"):
        rows += [f"**Native implementation:** `{item['implementation']}`", ""]

    if defect := catalog.get("native_defect"):
        rows += [
            f"**Native defect:** cannot work in AAUnlimited: {defect}. Any use is a strict error.",
            "",
        ]

    for form in item.get("receiver_forms", ()):
        receiver = form["receiver"]
        arguments = ", ".join(
            f"`{argument['name']}` is parameter {argument['parameter']} (`{argument['role']}`)"
            for argument in form["arguments"]
        )
        text = (
            f"**Receiver form:** `{form['signature']}` — receiver is native parameter "
            f"{receiver['parameter']} (`{receiver['role']}`); {arguments}"
        )
        rows += [text, ""]

    if values := catalog.get("event_values"):
        during = "; ".join(
            f"{type_name} during event{'s' if len(ids) > 1 else ''} {', '.join(map(str, ids))}"
            for type_name, ids in values["events"].items()
        )
        rows += [f"**Event values:** {during}; otherwise `{_value(values['otherwise'])}`", ""]

    if description := item.get("policy_description") or item.get("description"):
        rows += [description, ""]

    if "value" in item:
        if item["value"] is None and item["value_expression"] is not None:
            rows.append(f"**Native value expression:** `{item['value_expression']}`  ")
        else:
            value = json.dumps(item["value"], ensure_ascii=False, sort_keys=True)
            rows.append(f"**Value:** `{value}`  ")
        if item.get("resolved_value") is not None:
            rows.append(f"**Verified native value:** `{_value(item['resolved_value'])}`  ")
        rows += [f"**Duplicate-safe record:** `{item['anchor']}`", ""]

    if item.get("defaults"):
        defaults = ", ".join(
            f"parameter {default['parameter_index']} = `{_value(default['value'])}`"
            for default in item["defaults"]
        )
        rows += [f"**Source defaults:** {defaults}", ""]

    return rows


def _signature(
    item: dict[str, Any], key: str, name: str | None, member: dict[str, Any] | None
) -> str:
    parameters = _parameters(item)

    if name is None:
        signature = "raw form only"
    elif member is not None:
        signature = f"`{_member(member)}`"
    elif key == "events":
        signature = f"on `{name}{f'({parameters})' if parameters else ''}`"
    elif key == "named_constants" or (key == "expressions" and not parameters):
        signature = f"`{name}`"
    else:
        signature = f"`{name}({parameters})`"

    if result := item.get("return_type"):
        role = item.get("result_role")
        signature += f" → `{_source_type(result['name'], role)}`"
        if role not in {None, "card"}:
            signature += f" ({role})"

    return signature


def _parameters(item: dict[str, Any]) -> str:
    """``name: type (role) = default`` for each native parameter."""

    names = item.get("parameter_names")
    roles = item.get("parameter_roles") or ()
    defaults = {
        default["parameter_index"]: _value(default["value"]) for default in item.get("defaults", ())
    }

    parameters = []
    for index, argument in enumerate(item["parameter_types"]):
        role = roles[index] if index < len(roles) else None
        text = f"{names[index]}: " if names else ""
        text += _source_type(argument["name"], role)
        if role not in {None, "card"}:
            text += f" ({role})"
        if index in defaults:
            text += f" = {defaults[index]}"
        parameters.append(text)

    return ", ".join(parameters)


def _flags(item: dict[str, Any]) -> list[str]:
    names = item["source_names"]
    catalog = item.get("catalog", {})
    flags = []

    if any(names["ambiguity"].values()):
        flags.append("multiple candidates")
    if item.get("metadata_anomaly"):
        flags.append(f"declared return `{item['declared_return_type']['name']}` differs")
    if item.get("payload_marker"):
        flags.append(f"payload marker: {item['payload_kind']}")
    if catalog.get("native_defect"):
        flags.append("native defect (`NATIVE_DEFECTIVE_EXPRESSION`)")
    if catalog.get("row_status") in {"shadowed_value", "equivalent_duplicate"}:
        flags.append(catalog["row_status"])

    return flags


def _member(form: dict[str, Any]) -> str:
    """Typed member signature: ``<card>.SetVirtue(value: int)``, ``<card>.Virtue``."""

    if form["kind"] == "expression" and not form["arguments"]:
        return str(form["signature"])

    arguments = ", ".join(
        f"{item['name']}: {_source_type(item['type']['name'], item['role'])}"
        for item in form["arguments"]
    )
    return f"{form['signature'].split('(', 1)[0]}({arguments})"


def _source_type(kind: str, role: str | None) -> str:
    """A card-role ``int`` is written ``card`` in source; JSON keeps the wire type."""

    return "card" if kind == "int" and role == "card" else kind


def _value(value: dict[str, Any]) -> str:
    value_type = ValueType(value["type"])
    if value_type is ValueType.INVALID:
        return "invalid"
    if value_type is ValueType.BOOL:
        return "true" if value["value"] else "false"
    if value_type is ValueType.STRING:
        return json.dumps(value["value"], ensure_ascii=False)
    if value_type is ValueType.FLOAT and value.get("float_bits") is not None:
        return f"float_bits(0x{value['float_bits'] & 0xFFFFFFFF:08X})"
    return str(value["value"])
