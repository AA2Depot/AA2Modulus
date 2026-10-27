"""Compose the language catalog from registry facts and the validated policy."""

from __future__ import annotations

from dataclasses import replace
from threading import Lock
from types import MappingProxyType
from typing import Literal

from ...core.source_names import is_source_name, source_identifier
from ...metadata.fingerprint import canonical_hash, input_data
from ...metadata.identities import NativeKind, RowIdentity, WireIdentity, native_key
from ...metadata.snapshot import MetadataSnapshot
from ...model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ...model.types import EXPR_PAYLOAD_MARKERS, TypeId
from ..documentation import builtin_anchor
from ..policy import LanguagePolicy
from ..values import MemberForm
from .forms import target_forms
from .model import ConstantRow, LanguageCatalog, NativeTarget, SemanticSignature, SourceForm

_CATALOG_LIMIT = 8
_catalogs: dict[tuple[int, int], LanguageCatalog] = {}
_catalogs_lock = Lock()


def language_catalog(metadata: MetadataSnapshot, policy: LanguagePolicy) -> LanguageCatalog:
    """Return the catalog of ``metadata`` and ``policy``, built once per pair and process."""

    catalog = _cached_catalog(metadata, policy)
    if catalog is None:
        with _catalogs_lock:
            catalog = _cached_catalog(metadata, policy)
            if catalog is None:
                catalog = build_language_catalog(metadata, policy)
                if len(_catalogs) >= _CATALOG_LIMIT:
                    _catalogs.clear()
                _catalogs[id(metadata), id(policy)] = catalog
    return catalog


def _cached_catalog(metadata: MetadataSnapshot, policy: LanguagePolicy) -> LanguageCatalog | None:
    catalog = _catalogs.get((id(metadata), id(policy)))
    if catalog is not None and catalog.metadata is metadata and catalog.policy is policy:
        return catalog
    return None


def build_language_catalog(metadata: MetadataSnapshot, policy: LanguagePolicy) -> LanguageCatalog:
    targets = _regular_targets(metadata, policy)
    constant_rows = _constant_targets(metadata, targets)
    rejected = _rejected_constant_names(constant_rows, policy)
    forms, names, retired_by_target = _attach_forms(targets, metadata, policy)
    retired, retired_members = _retired_spellings(targets, names, retired_by_target)
    return LanguageCatalog(
        metadata,
        policy,
        MappingProxyType(targets),
        tuple(constant_rows),
        MappingProxyType(forms),
        canonical_hash({"facts": metadata.fingerprint, "policy": input_data(policy)}),
        MappingProxyType({key: tuple(dict.fromkeys(values)) for key, values in names.items()}),
        MappingProxyType(rejected),
        MappingProxyType({key: tuple(dict.fromkeys(value)) for key, value in retired.items()}),
        MappingProxyType(
            {key: tuple(dict.fromkeys(value)) for key, value in retired_members.items()}
        ),
    )


def _regular_targets(
    metadata: MetadataSnapshot, policy: LanguagePolicy
) -> dict[WireIdentity, NativeTarget]:
    """Actions, events and expressions, keyed by wire identity."""

    targets: dict[WireIdentity, NativeTarget] = {}
    regular: tuple[ActionMetadata | EventMetadata | ExpressionMetadata, ...] = (
        *metadata.actions,
        *metadata.events,
        *metadata.expressions,
    )
    for entry in regular:
        wire = native_key(entry)
        row = RowIdentity(wire.kind, entry.id, wire.scope)
        result_type = entry.return_type if isinstance(entry, ExpressionMetadata) else None
        defaults = tuple(
            (default.parameter_index, default.value)
            for default in policy.action_defaults
            if isinstance(entry, ActionMetadata) and default.action_id == entry.id
        )
        signature = SemanticSignature(entry.parameter_types, result_type, defaults)
        declared = entry.declared_return_type if isinstance(entry, ExpressionMetadata) else None
        save = (
            WireIdentity(wire.kind, entry.id, declared)
            if isinstance(entry, ExpressionMetadata)
            else wire
        )
        reload_entry = (
            metadata.expression(declared, entry.id)
            if isinstance(entry, ExpressionMetadata) and declared is not None
            else entry
        )
        reload = (
            None if reload_entry is None else RowIdentity(wire.kind, reload_entry.id, save.scope)
        )
        targets[wire] = NativeTarget(
            wire,
            row,
            entry,
            signature,
            declared,
            save,
            reload,
            builtin_anchor(entry),
            policy.event_values(wire),
        )
    return targets


def _constant_targets(
    metadata: MetadataSnapshot, targets: dict[WireIdentity, NativeTarget]
) -> list[ConstantRow]:
    """Add every named-constant wire ID to ``targets`` and describe each registry row."""

    scoped: dict[TypeId, list[NamedConstantMetadata]] = {}
    for constant in metadata.named_constants:
        scoped.setdefault(constant.value_type, []).append(constant)
    constant_rows: list[ConstantRow] = []
    for scope, entries in scoped.items():
        first: dict[int, int] = {}
        for ordinal, constant in enumerate(entries, 1):
            first.setdefault(constant.id, ordinal)
        selected_wires: dict[int, list[int]] = {}
        for identifier in sorted(set(first) | set(range(1, len(entries) + 1))):
            ordinal = first.get(identifier, identifier)
            constant_entry = entries[ordinal - 1]
            wire = WireIdentity("named_constant", identifier, scope)
            row = RowIdentity("named_constant", ordinal, scope)
            save = WireIdentity("named_constant", constant_entry.id, scope)
            reload = RowIdentity("named_constant", first[constant_entry.id], scope)
            targets[wire] = NativeTarget(
                wire,
                row,
                constant_entry,
                SemanticSignature((), scope),
                scope,
                save,
                reload,
                builtin_anchor(constant_entry, ordinal=ordinal),
            )
            selected_wires.setdefault(ordinal, []).append(identifier)
        for ordinal, constant_entry in enumerate(entries, 1):
            winner = first[constant_entry.id]
            winner_value = entries[winner - 1].resolved_value
            status: Literal[
                "first_row", "equivalent_duplicate", "shadowed_value", "unverified_value"
            ] = (
                "first_row"
                if winner == ordinal
                else "unverified_value"
                if winner_value is None or constant_entry.resolved_value is None
                else "equivalent_duplicate"
                if winner_value == constant_entry.resolved_value
                else "shadowed_value"
            )
            constant_rows.append(
                ConstantRow(
                    RowIdentity("named_constant", ordinal, scope),
                    constant_entry,
                    RowIdentity("named_constant", winner, scope),
                    status,
                    tuple(selected_wires.get(ordinal, ())),
                    builtin_anchor(constant_entry, ordinal=ordinal),
                )
            )
    return constant_rows


def _rejected_constant_names(
    constant_rows: list[ConstantRow], policy: LanguagePolicy
) -> dict[tuple[str, TypeId], tuple[str, str]]:
    """Native names of shadowed or unverified rows, with the reason and a suggestion."""

    rejected: dict[tuple[str, TypeId], tuple[str, str]] = {}
    for constant_row in constant_rows:
        if constant_row.status not in {"shadowed_value", "unverified_value"}:
            continue
        aliases = (
            source_identifier(constant_row.metadata.name),
            constant_row.metadata.name,
            constant_row.metadata.interactive_name,
        )
        value = next(
            (item for item in policy.source_values if item.row == constant_row.identity), None
        )
        suggestion = (
            f"use {value.name} for the verified literal value"
            if value
            else "use a verified source value constant"
        )
        for alias in aliases:
            if is_source_name(alias):
                rejected[(alias.casefold(), constant_row.metadata.value_type)] = (
                    f"shadowed native constant alias {alias!r} cannot select its row value",
                    suggestion,
                )
    return rejected


def _attach_forms(
    targets: dict[WireIdentity, NativeTarget], metadata: MetadataSnapshot, policy: LanguagePolicy
) -> tuple[
    dict[str, SourceForm],
    dict[tuple[NativeKind, str], list[WireIdentity]],
    dict[WireIdentity, tuple[str, ...]],
]:
    """Give each target its forms; index forms and flat spellings."""

    forms: dict[str, SourceForm] = {}
    names: dict[tuple[NativeKind, str], list[WireIdentity]] = {}
    retired_by_target: dict[WireIdentity, tuple[str, ...]] = {}
    for wire, target in tuple(targets.items()):
        source_forms, retired_spellings = target_forms(target, metadata, policy)
        retired_by_target[wire] = retired_spellings
        reason = (
            None if any(form.canonical for form in source_forms) else "no_reversible_named_form"
        )
        if wire.kind == "expression" and wire.identifier in EXPR_PAYLOAD_MARKERS:
            reason = "serialized_payload_marker"
        targets[wire] = replace(target, forms=source_forms, source_reason=reason)
        for form in source_forms:
            forms[form.key] = form
            if form.kind == "member":
                continue
            names.setdefault((wire.kind, form.spelling.casefold()), []).append(wire)
    return forms, names, retired_by_target


def _retired_spellings(
    targets: dict[WireIdentity, NativeTarget],
    names: dict[tuple[NativeKind, str], list[WireIdentity]],
    retired_by_target: dict[WireIdentity, tuple[str, ...]],
) -> tuple[dict[tuple[NativeKind, str], list[str]], dict[tuple[NativeKind, str], list[MemberForm]]]:
    """Retired flat spellings mapped to their canonical spelling or member form."""

    retired: dict[tuple[NativeKind, str], list[str]] = {}
    retired_members: dict[tuple[NativeKind, str], list[MemberForm]] = {}
    for wire, spellings in retired_by_target.items():
        canonical = targets[wire].canonical_form
        if canonical is not None and canonical.kind == "member":
            assert canonical.member is not None
            for spelling in spellings:
                retired_members.setdefault((wire.kind, spelling.casefold()), []).append(
                    canonical.member
                )
            continue
        if canonical is None:
            continue
        for spelling in spellings:
            key = (wire.kind, spelling.casefold())
            if key not in names:
                retired.setdefault(key, []).append(canonical.spelling)
    return retired, retired_members
