"""reference.json: every native row with its source names, policy and catalog facts"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from aa2modulus.context.operation import SourceContext
from aa2modulus.language.documentation import builtin_anchor, constant_ordinals
from aa2modulus.language.loader import LANGUAGE_POLICY
from aa2modulus.language.values import EventValues, MemberForm
from aa2modulus.metadata.fingerprint import input_data
from aa2modulus.metadata.identities import WireIdentity, native_key
from aa2modulus.metadata.schema import FILE_SCHEMAS
from aa2modulus.model.native import ActionMetadata, ExpressionMetadata, NamedConstantMetadata
from aa2modulus.model.types import (
    EXPR_CONSTANT,
    EXPR_NAMEDCONSTANT,
    EXPR_PAYLOAD_MARKERS,
    EXPR_VAR,
    ValueType,
)

from .bundle import DOCS, GRAMMAR, examples
from .names import source_names

SCHEMA = "aa2modulus.language-reference.v8"
PAYLOAD_KINDS = {
    EXPR_CONSTANT: "constant",
    EXPR_VAR: "variable",
    EXPR_NAMEDCONSTANT: "named_constant",
}


def build(root: Path, *, context: SourceContext | None = None) -> dict[str, Any]:
    """The portable reference data: types, native rows with their source spellings, and policy."""

    context = context or SourceContext.create()
    snapshot = context.metadata
    policy = context.source_policy
    catalog = context.catalog

    # Constants are numbered by their position within each value type.
    constants = sorted(
        constant_ordinals(snapshot.named_constants), key=lambda pair: pair[0].value_type
    )

    return {
        "schema": SCHEMA,
        "language_version": policy.language_version,
        "provenance": _provenance(root, context),
        "types": [
            {"id": int(item), "name": item.name.lower()}
            for item in ValueType
            if item is not ValueType.N_TYPES
        ],
        "expression_payload_markers": [
            {"id": identifier, "kind": kind} for identifier, kind in PAYLOAD_KINDS.items()
        ],
        "actions": [
            _record(item, item.id, context)
            for item in sorted(snapshot.actions, key=lambda item: item.id)
        ],
        "events": [
            _record(item, item.id, context)
            for item in sorted(snapshot.events, key=lambda item: item.id)
        ],
        "expressions": [
            _record(item, item.id, context)
            for item in sorted(
                snapshot.expressions, key=lambda item: (int(item.return_type), item.id)
            )
        ],
        "named_constants": [_record(item, ordinal, context) for item, ordinal in constants],
        "operators": [
            {
                "token": item.token,
                "expression_id": item.expression_id,
                "return_type": _type(item.return_type),
                "parameter_types": [_type(value) for value in item.parameter_types],
                "precedence": item.precedence,
                "associativity": item.associativity,
                "fixity": item.fixity,
                "short_circuit": item.short_circuit,
                "native_name": item.source_name,
            }
            for item in policy.operators
        ],
        "constant_wire_lookups": [
            _lookup(target)
            for target in catalog.native_targets.values()
            if target.wire.kind == "named_constant"
        ],
        "source_values": [
            {
                "name": value.name,
                "row": input_data(value.row),
                "value": value.value.to_ir(),
                "documentation_key": value.documentation_key,
            }
            for value in catalog.source_values
        ],
        "readable_expressions": [
            input_data(WireIdentity("expression", identifier, scope))
            for scope, identifier in policy.readable_expressions
        ],
        "expression_defects": [
            {
                "target": input_data(WireIdentity("expression", identifier, scope)),
                "declared_parameter_types": [int(item) for item in declared],
                "reason": reason,
            }
            for scope, identifier, declared, reason in policy.expression_defects
        ],
        "receiver_forms": [member_form(form) for form in policy.member_forms],
    }


def _provenance(root: Path, context: SourceContext) -> dict[str, Any]:
    snapshot = context.metadata
    registry = root / "aa2modulus/metadata/registry"
    policy = root / "aa2modulus/language" / LANGUAGE_POLICY
    sources = [*(root / "docs" / name for name in DOCS), root / GRAMMAR, *examples(root)]

    return {
        "source_revision": snapshot.source_revision,
        "registry_generator_version": snapshot.generator_version,
        "fact_fingerprint": snapshot.fingerprint,
        "catalog_fingerprint": context.catalog.fingerprint,
        "native_source_sha256": dict(snapshot.source_sha256),
        "sha256": {name: _hash(registry / name) for name in ("manifest.json", *FILE_SCHEMAS)}
        | {policy.name: _hash(policy)},
        "documentation_sha256": {name: _hash(root / "docs" / name) for name in DOCS},
        "bundle_source_sha256": {
            path.relative_to(root).as_posix(): _hash(path) for path in sources
        },
    }


def _record(entry: Any, ordinal: int, context: SourceContext) -> dict[str, Any]:
    policy = context.source_policy
    wire = native_key(entry)

    record: dict[str, Any] = {
        "ordinal": ordinal,
        "anchor": builtin_anchor(entry, ordinal=ordinal),
        "id": entry.id,
        "scope": None if wire.scope is None else _type(wire.scope),
        "registry_index": ordinal if isinstance(entry, NamedConstantMetadata) else entry.id,
        "name": entry.name,
        "interactive_name": entry.interactive_name,
        "description": entry.description,
        "category": entry.category,
        "parameter_types": [_type(item) for item in getattr(entry, "parameter_types", ())],
        "source_names": source_names(entry, context.catalog),
        "registration_provenance": input_data(entry.provenance),
        "policy_description": policy.description_override(wire),
    }

    if isinstance(entry, (ActionMetadata, ExpressionMetadata)):
        names = policy.parameter_names(wire)
        roles = policy.parameter_roles(wire)
        record["parameter_names"] = None if names is None else list(names)
        record["parameter_roles"] = None if roles is None else list(roles)
        record["receiver_forms"] = [
            member_form(form) for form in policy.member_forms if form.target == wire
        ]

    if isinstance(entry, ActionMetadata):
        record["implementation"] = entry.implementation
        record["defaults"] = [
            {"parameter_index": default.parameter_index, "value": default.value.to_ir()}
            for default in sorted(
                policy.action_defaults, key=lambda default: default.parameter_index
            )
            if default.action_id == entry.id
        ]

    if isinstance(entry, ExpressionMetadata):
        assert entry.declared_return_type is not None
        record["return_type"] = _type(entry.return_type)
        record["declared_return_type"] = _type(entry.declared_return_type)
        record["record_ordinal_in_scope"] = ordinal
        record["payload_marker"] = entry.id in EXPR_PAYLOAD_MARKERS
        record["payload_kind"] = PAYLOAD_KINDS.get(entry.id)
        record["metadata_anomaly"] = entry.declared_return_type != entry.return_type
        record["implementation"] = entry.implementation
        record["result_role"] = policy.expression_result_role(entry.return_type, entry.id)

    if isinstance(entry, NamedConstantMetadata):
        record["value"] = None if entry.value is None else entry.value.to_ir()
        record["value_expression"] = entry.value_expression
        record["resolved_value"] = (
            None if entry.resolved_value is None else entry.resolved_value.to_ir()
        )
        record["record_ordinal_in_scope"] = ordinal

    record["catalog"] = _catalog(entry, record, context)
    return record


def _catalog(entry: Any, record: dict[str, Any], context: SourceContext) -> dict[str, Any]:
    """How the catalog resolves and saves this row's wire identity."""

    catalog = context.catalog
    wire = native_key(entry)
    target = catalog.native_targets[wire]

    facts = {
        **_lookup(target),
        "candidate_forms": input_data(target.forms),
        "source_reason": target.source_reason,
        "event_values": _event_values(target.event_values),
    }

    if wire.kind == "expression" and wire.scope is not None:
        defect = catalog.expression_defect(wire.scope, wire.identifier)
        if defect is not None:
            facts["native_defect"] = defect

    if wire.kind == "named_constant":
        row = next(
            row for row in catalog.constant_rows if row.documentation_key == record["anchor"]
        )
        facts["row_status"] = row.status
        facts["selecting_wire_ids"] = row.selecting_wire_ids

    return facts


def _event_values(values: EventValues | None) -> dict[str, Any] | None:
    """Policy ``[event_values]``: the type the callback returns in which events."""

    if values is None:
        return None
    return {
        "callback": values.callback,
        "events": {ValueType(scope).name.lower(): list(ids) for scope, ids in values.events},
        "otherwise": values.otherwise.to_ir(),
    }


def _lookup(target: Any) -> dict[str, Any]:
    """Native lookup and re-save of one wire identity."""

    return {
        "wire": input_data(target.wire),
        "lookup_row": input_data(target.row),
        "save_identity": input_data(target.save_identity),
        "reload_row": input_data(target.reload_row),
    }


def member_form(form: MemberForm) -> dict[str, Any]:
    return {
        "key": form.key,
        "member": form.name,
        "kind": form.target.kind,
        "receiver": {
            "parameter": form.receiver_parameter,
            "role": form.receiver_role,
            "type": _type(form.receiver_type),
        },
        "arguments": [
            {
                "parameter": item.parameter,
                "name": item.name,
                "role": item.role,
                "type": _type(form.parameter_types[item.parameter]),
            }
            for item in form.arguments
        ],
        "result_type": None if form.result_type is None else _type(form.result_type),
        "signature": _member_signature(form),
    }


def _member_signature(form: MemberForm) -> str:
    """``<card>.SetVirtue(value)`` for calls, ``<card>.Virtue`` for property reads."""

    name = f"<{form.receiver_role}>.{form.name}"
    if form.target.kind == "expression" and not form.arguments:
        return name
    return f"{name}({', '.join(item.name for item in form.arguments)})"


def _type(value: int | ValueType) -> dict[str, int | str]:
    return {"id": int(value), "name": ValueType(value).name.lower()}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
