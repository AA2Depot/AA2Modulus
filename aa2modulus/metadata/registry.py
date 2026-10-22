"""Validate registry JSON and construct typed entries before immutable indexing."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..model.native import (
    ActionMetadata,
    EventMetadata,
    ExpressionMetadata,
    NamedConstantMetadata,
    RegistryProvenance,
)
from ..model.types import ValueType
from ..model.values import Value
from .checks import (
    load_json,
    require_array,
    require_digest,
    require_fields,
    require_int,
    require_int32,
    require_mapping,
    require_string,
)
from .fingerprint import canonical_hash
from .schema import (
    FILE_SCHEMAS,
    GENERATOR_VERSION,
    MANIFEST_SCHEMA,
    SCOPE_TYPES,
    MetadataError,
)

_SCOPE_IDS = frozenset(SCOPE_TYPES.values())
_SCOPE_NAMES = {identifier: name for name, identifier in SCOPE_TYPES.items()}


@dataclass(frozen=True, slots=True)
class RegistryEntries:
    """Typed catalog data; no lookup indexes or source policy."""

    source_revision: str
    generator_version: str
    actions: tuple[ActionMetadata, ...]
    events: tuple[EventMetadata, ...]
    expressions: tuple[ExpressionMetadata, ...]
    named_constants: tuple[NamedConstantMetadata, ...]
    source_sha256: tuple[tuple[str, str], ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _RegistryDocument:
    entries: Mapping[str, object]
    categories: Mapping[int, str]


@dataclass(frozen=True, slots=True)
class _RawEntry:
    label: str
    data: Mapping[str, object]
    key_id: int | None = None
    scope_id: int | None = None
    registry_position: int | None = None


def _source_hashes(value: object, label: str) -> dict[str, str]:
    mapping = require_mapping(value, label)
    if not mapping:
        raise MetadataError(f"{label} must not be empty")
    hashes: dict[str, str] = {}
    for path, digest in mapping.items():
        if not path.startswith("AAUnlimited/") or ".." in path.split("/") or "\\" in path:
            raise MetadataError(f"{label}.{path} must be a relative native source path")
        hashes[path] = require_digest(digest, f"{label}.{path}")
    return hashes


def _provenance(entry: Mapping[str, object], label: str) -> RegistryProvenance:
    raw = require_mapping(entry.get("provenance"), f"{label}.provenance")
    require_fields(raw, f"{label}.provenance", {"source_file", "registration_sha256"})
    path = require_string(raw.get("source_file"), f"{label}.provenance.source_file")
    if not path.startswith("AAUnlimited/") or ".." in path.split("/") or "\\" in path:
        raise MetadataError(f"{label}.provenance.source_file must be a relative native source path")
    return RegistryProvenance(
        path,
        require_digest(raw.get("registration_sha256"), f"{label}.provenance.registration_sha256"),
    )


def _implementation(entry: Mapping[str, object], label: str) -> str | None:
    raw = entry.get("implementation")
    if raw is None:
        return None
    text = require_string(raw, f"{label}.implementation")
    if re.fullmatch(r"Thread::[A-Za-z_][A-Za-z0-9_]*", text) is None:
        raise MetadataError(f"{label}.implementation must identify a native Thread callback")
    return text


def _type_id(value: object, label: str) -> ValueType:
    raw = require_int(value, label)
    if raw not in _SCOPE_IDS:
        raise MetadataError(f"{label} has unsupported type id {raw}")
    try:
        return ValueType(raw)
    except ValueError as exc:
        raise MetadataError(f"{label} has unsupported type id {raw}") from exc


def _parameter_types(value: object, label: str) -> tuple[int | ValueType, ...]:
    if not isinstance(value, list):
        raise MetadataError(f"{label} must be an array")
    return tuple(_type_id(item, f"{label}[{index}]") for index, item in enumerate(value))


def _category(value: object, label: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise MetadataError(f"{label} must be a string or null")
    return value


def _entry_common(
    entry: Mapping[str, object], label: str
) -> tuple[int, str, str, str, str | None, tuple[int | ValueType, ...]]:
    return (
        require_int(entry.get("id"), f"{label}.id"),
        require_string(entry.get("name"), f"{label}.name"),
        require_string(entry.get("interactive_name"), f"{label}.interactive_name"),
        require_string(entry.get("description"), f"{label}.description"),
        _category(entry.get("category"), f"{label}.category"),
        _parameter_types(entry.get("parameter_types"), f"{label}.parameter_types"),
    )


def _identity_key(value: object, label: str) -> int:
    text = require_string(value, label)
    try:
        identifier = int(text)
    except ValueError as exc:
        raise MetadataError(f"{label} must be a decimal integer key") from exc
    if str(identifier) != text:
        raise MetadataError(f"{label} must use the canonical decimal integer form")
    return identifier


def _validate_registry_identity(entry: Mapping[str, object], identifier: int, label: str) -> None:
    if identifier <= 0:
        raise MetadataError(f"{label}.id must be positive")
    require_int32(identifier, f"{label}.id")
    registry_index = require_int(entry.get("registry_index"), f"{label}.registry_index")
    if registry_index <= 0 or registry_index != identifier:
        raise MetadataError(f"{label}.registry_index must be the positive entry id")


def _validate_categories(document: Mapping[str, object], filename: str) -> dict[int, str]:
    label = f"{filename}.categories"
    raw_categories = document.get("categories")
    if not isinstance(raw_categories, list):
        raise MetadataError(f"{label} must be an array")
    categories: dict[int, str] = {}
    for position, raw_category in enumerate(raw_categories, start=1):
        item_label = f"{label}[{position}]"
        category = require_mapping(raw_category, item_label)
        require_fields(category, item_label, {"id", "name"})
        identifier = require_int(category.get("id"), f"{item_label}.id")
        name = require_string(category.get("name"), f"{item_label}.name")
        if identifier in categories:
            raise MetadataError(f"{item_label}.id duplicates category id {identifier}")
        categories[identifier] = name
    return categories


def _validate_entry_category(
    entry: Mapping[str, object], categories: Mapping[int, str], label: str
) -> None:
    category_id = require_int(entry.get("category_id"), f"{label}.category_id")
    category = require_string(entry.get("category"), f"{label}.category")
    if categories.get(category_id) != category:
        raise MetadataError(f"{label}.category_id does not identify {label}.category")


def _value_from_ir(data: Mapping[str, object], label: str, scope_id: int) -> Value:
    value_type = _type_id(data.get("type"), f"{label}.type")
    if int(value_type) != scope_id:
        raise MetadataError(f"{label}.type does not match its named constant scope")
    if value_type is ValueType.FLOAT and "float_bits" in data:
        expected_fields = {"type", "value", "float_bits"}
        if data.get("value") is not None:
            raise MetadataError(f"{label}.value must be null when float_bits is present")
        require_int(data.get("float_bits"), f"{label}.float_bits")
    else:
        expected_fields = {"type", "value"}
    extra = set(data) - expected_fields
    missing = expected_fields - set(data)
    if extra:
        field = min(extra)
        raise MetadataError(f"{label}.{field} is not part of the value IR shape")
    if missing:
        field = min(missing)
        raise MetadataError(f"{label}.{field} is required")
    payload = data["value"]
    if value_type is ValueType.INVALID and payload is not None:
        raise MetadataError(f"{label}.value must be null for invalid values")
    if value_type is ValueType.INT:
        require_int32(payload, f"{label}.value")
    elif value_type is ValueType.BOOL and not isinstance(payload, bool):
        raise MetadataError(f"{label}.value must be a boolean")
    elif value_type is ValueType.FLOAT and "float_bits" not in data:
        if isinstance(payload, bool) or not isinstance(payload, float):
            raise MetadataError(f"{label}.value must be a float")
    elif value_type is ValueType.STRING and not isinstance(payload, str):
        raise MetadataError(f"{label}.value must be a string")
    try:
        return Value.from_ir(data)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MetadataError(f"{label}: {exc}") from exc


def _load_documents(
    directory: Path,
    file_info: Mapping[str, object],
    source_revision: str,
    generator_version: str,
) -> dict[str, _RegistryDocument]:
    loaded: dict[str, _RegistryDocument] = {}
    for filename, schema in FILE_SCHEMAS.items():
        info = require_mapping(file_info.get(filename), f"manifest.json.files.{filename}")
        require_fields(info, f"manifest.json.files.{filename}", {"entry_count"})
        expected_count = require_int(
            info.get("entry_count"), f"manifest.json.files.{filename}.entry_count"
        )
        if expected_count < 0:
            raise MetadataError(f"manifest.json.files.{filename}.entry_count must be nonnegative")
        document = load_json(directory / filename)
        require_fields(
            document,
            filename,
            {"schema", "source_revision", "generator_version", "entries", "categories"},
        )
        for field, expected in (
            ("schema", schema),
            ("source_revision", source_revision),
            ("generator_version", generator_version),
        ):
            actual = require_string(document.get(field), f"{filename}.{field}")
            if actual != expected:
                raise MetadataError(
                    f"{filename}.{field} mismatch: expected {expected!r}, got {actual!r}"
                )
        categories = _validate_categories(document, filename)
        raw_entry_map = require_mapping(document.get("entries"), f"{filename}.entries")
        if filename in {"expressions.json", "named_constants.json"}:
            actual_count = 0
            for scope_name, scope in raw_entry_map.items():
                if scope_name not in SCOPE_TYPES:
                    raise MetadataError(
                        f"{filename}.entries.{scope_name} is an unsupported type scope"
                    )
                if filename == "expressions.json":
                    actual_count += len(require_mapping(scope, f"{filename}.entries.{scope_name}"))
                else:
                    actual_count += len(require_array(scope, f"{filename}.entries.{scope_name}"))
        else:
            actual_count = len(raw_entry_map)
        if actual_count != expected_count:
            raise MetadataError(
                f"manifest.json.files.{filename}.entry_count does not match {filename}.entries"
            )
        loaded[filename] = _RegistryDocument(entries=raw_entry_map, categories=categories)

    return loaded


def _raw_entries(document: _RegistryDocument, filename: str) -> list[_RawEntry]:
    entries_value = document.entries
    output: list[_RawEntry] = []
    if filename in {"actions.json", "events.json"}:
        for key, raw in entries_value.items():
            label = f"{filename}.entries.{key}"
            key_id = _identity_key(key, f"{label}.<key>")
            output.append(_RawEntry(label=label, data=require_mapping(raw, label), key_id=key_id))
    elif filename == "expressions.json":
        for scope_name, raw_scope in entries_value.items():
            scope_id = SCOPE_TYPES[scope_name]
            scope = require_mapping(raw_scope, f"{filename}.entries.{scope_name}")
            for key, raw in scope.items():
                label = f"{filename}.entries.{scope_name}.{key}"
                key_id = _identity_key(key, f"{label}.<key>")
                output.append(
                    _RawEntry(
                        label=label,
                        data=require_mapping(raw, label),
                        key_id=key_id,
                        scope_id=scope_id,
                    )
                )
    else:
        for scope_name, raw_scope in entries_value.items():
            scope_id = SCOPE_TYPES[scope_name]
            scope_items = require_array(raw_scope, f"{filename}.entries.{scope_name}")
            for position, raw in enumerate(scope_items, start=1):
                label = f"{filename}.entries.{scope_name}[{position}]"
                output.append(
                    _RawEntry(
                        label=label,
                        data=require_mapping(raw, label),
                        scope_id=scope_id,
                        registry_position=position,
                    )
                )
    common = {
        "id",
        "name",
        "interactive_name",
        "description",
        "category",
        "category_id",
        "registry_index",
        "provenance",
    }
    extra_fields = {
        "actions.json": {"parameter_types", "implementation"},
        "events.json": {"parameter_types", "symbol"},
        "expressions.json": {
            "parameter_types",
            "return_type",
            "return_type_name",
            "declared_return_type",
            "implementation",
        },
        "named_constants.json": {"value_type", "value_type_name", "value", "resolved_value"},
    }
    optional = {"value_expression"} if filename == "named_constants.json" else set()
    for raw in output:
        require_fields(raw.data, raw.label, common | extra_fields[filename], optional)
    return output


def _read_actions(document: _RegistryDocument) -> tuple[ActionMetadata, ...]:
    actions: list[ActionMetadata] = []
    for raw in _raw_entries(document, "actions.json"):
        label, entry = raw.label, raw.data
        action_key_id = raw.key_id
        identifier, name, interactive, description, category, parameter_types = _entry_common(
            entry, label
        )
        if identifier != action_key_id:
            raise MetadataError(f"{label}.id does not match its key")
        _validate_registry_identity(entry, identifier, label)
        _validate_entry_category(entry, document.categories, label)
        actions.append(
            ActionMetadata(
                id=identifier,
                name=name,
                interactive_name=interactive,
                description=description,
                category=category,
                parameter_types=parameter_types,
                implementation=_implementation(entry, label),
                provenance=_provenance(entry, label),
            )
        )

    return tuple(actions)


def _read_events(document: _RegistryDocument) -> tuple[EventMetadata, ...]:
    events: list[EventMetadata] = []
    for raw in _raw_entries(document, "events.json"):
        label, entry = raw.label, raw.data
        event_key_id = raw.key_id
        identifier, name, interactive, description, category, parameter_types = _entry_common(
            entry, label
        )
        if identifier != event_key_id:
            raise MetadataError(f"{label}.id does not match its key")
        _validate_registry_identity(entry, identifier, label)
        _validate_entry_category(entry, document.categories, label)
        symbol = require_string(entry.get("symbol"), f"{label}.symbol")
        if not symbol:
            raise MetadataError(f"{label}.symbol must not be empty")
        events.append(
            EventMetadata(
                id=identifier,
                name=name,
                interactive_name=interactive,
                description=description,
                category=category,
                parameter_types=parameter_types,
                symbol=symbol,
                provenance=_provenance(entry, label),
            )
        )

    return tuple(events)


def _read_expressions(document: _RegistryDocument) -> tuple[ExpressionMetadata, ...]:
    expressions: list[ExpressionMetadata] = []
    for raw in _raw_entries(document, "expressions.json"):
        label, entry = raw.label, raw.data
        scope_id = raw.scope_id
        expression_key_id = raw.key_id
        assert scope_id is not None
        identifier, name, interactive, description, category, parameter_types = _entry_common(
            entry, label
        )
        if identifier != expression_key_id:
            raise MetadataError(f"{label}.id does not match its key")
        _validate_registry_identity(entry, identifier, label)
        return_type = _type_id(entry.get("return_type"), f"{label}.return_type")
        if int(return_type) != scope_id:
            raise MetadataError(f"{label}.return_type does not match its scope")
        type_name = require_string(entry.get("return_type_name"), f"{label}.return_type_name")
        if type_name != _SCOPE_NAMES[scope_id]:
            raise MetadataError(f"{label}.return_type_name does not match its scope")
        declared_return_type = _type_id(
            entry.get("declared_return_type"), f"{label}.declared_return_type"
        )
        _validate_entry_category(entry, document.categories, label)
        expressions.append(
            ExpressionMetadata(
                id=identifier,
                return_type=return_type,
                name=name,
                interactive_name=interactive,
                description=description,
                category=category,
                parameter_types=parameter_types,
                declared_return_type=declared_return_type,
                implementation=_implementation(entry, label),
                provenance=_provenance(entry, label),
            )
        )

    return tuple(expressions)


def _read_named_constants(document: _RegistryDocument) -> tuple[NamedConstantMetadata, ...]:
    named_constants: list[NamedConstantMetadata] = []
    for raw in _raw_entries(document, "named_constants.json"):
        label, entry = raw.label, raw.data
        scope_id = raw.scope_id
        position = raw.registry_position
        assert scope_id is not None
        identifier = require_int32(entry.get("id"), f"{label}.id")
        if identifier <= 0:
            raise MetadataError(f"{label}.id must be positive")
        name = require_string(entry.get("name"), f"{label}.name")
        interactive = require_string(entry.get("interactive_name"), f"{label}.interactive_name")
        description = require_string(entry.get("description"), f"{label}.description")
        category = _category(entry.get("category"), f"{label}.category")
        value_type = _type_id(entry.get("value_type"), f"{label}.value_type")
        if int(value_type) != scope_id:
            raise MetadataError(f"{label}.value_type does not match its scope")
        type_name = require_string(entry.get("value_type_name"), f"{label}.value_type_name")
        if type_name != _SCOPE_NAMES[scope_id]:
            raise MetadataError(f"{label}.value_type_name does not match its scope")
        registry_index = require_int(entry.get("registry_index"), f"{label}.registry_index")
        assert position is not None
        if registry_index != position:
            raise MetadataError(f"{label}.registry_index must equal its 1-based list position")
        _validate_entry_category(entry, document.categories, label)
        raw_value = entry.get("value")
        if raw_value is None:
            value = None
        else:
            value_label = f"{label}.value"
            value_data = require_mapping(raw_value, value_label)
            value = _value_from_ir(value_data, value_label, scope_id)
        value_expression = entry.get("value_expression")
        if value_expression is not None and not isinstance(value_expression, str):
            raise MetadataError(f"{label}.value_expression must be a string or null")
        resolved_raw = entry.get("resolved_value")
        resolved_value = (
            None
            if resolved_raw is None
            else _value_from_ir(
                require_mapping(resolved_raw, f"{label}.resolved_value"),
                f"{label}.resolved_value",
                scope_id,
            )
        )
        if value is not None and resolved_value != value:
            raise MetadataError(f"{label}.resolved_value disagrees with the native literal value")
        metadata = NamedConstantMetadata(
            id=identifier,
            value_type=value_type,
            name=name,
            interactive_name=interactive,
            description=description,
            category=category,
            value=value,
            value_expression=value_expression,
            resolved_value=resolved_value,
            provenance=_provenance(entry, label),
        )
        named_constants.append(metadata)

    return tuple(named_constants)


def load_registry(directory: Path) -> RegistryEntries:
    """Read and validate complete catalog files, retaining file/field diagnostics."""

    try:
        manifest = load_json(directory / "manifest.json")
        schema = require_string(manifest.get("schema"), "manifest.json.schema")
        if schema != MANIFEST_SCHEMA:
            raise MetadataError(
                f"manifest.json.schema mismatch: expected {MANIFEST_SCHEMA!r}, got {schema!r}"
            )
        return _read_registry(directory, manifest)
    except MetadataError as exc:
        message = str(exc)
        for filename in ("manifest.json", *FILE_SCHEMAS):
            if message.startswith(f"{filename}."):
                raise MetadataError(f"{directory / filename}: {message}") from exc
        raise


def _read_registry(directory: Path, manifest: Mapping[str, object]) -> RegistryEntries:
    require_fields(
        manifest,
        "manifest.json",
        {"schema", "source_revision", "generator_version", "files", "source_sha256"},
    )
    source_revision = require_string(
        manifest.get("source_revision"), "manifest.json.source_revision"
    )
    if not source_revision:
        raise MetadataError("manifest.json.source_revision must not be empty")
    generator_version = require_string(
        manifest.get("generator_version"), "manifest.json.generator_version"
    )
    if generator_version != GENERATOR_VERSION:
        raise MetadataError(
            f"manifest.json.generator_version must be {GENERATOR_VERSION!r}, got "
            f"{generator_version!r}"
        )
    file_info = require_mapping(manifest.get("files"), "manifest.json.files")
    if set(file_info) != set(FILE_SCHEMAS):
        raise MetadataError("manifest.json.files must list exactly the supported registry files")

    documents = _load_documents(directory, file_info, source_revision, generator_version)
    source_hashes = _source_hashes(manifest.get("source_sha256"), "manifest.json.source_sha256")
    actions = _read_actions(documents["actions.json"])
    events = _read_events(documents["events.json"])
    expressions = _read_expressions(documents["expressions.json"])
    constants = _read_named_constants(documents["named_constants.json"])
    native_entries: tuple[
        ActionMetadata | EventMetadata | ExpressionMetadata | NamedConstantMetadata, ...
    ] = (*actions, *events, *expressions, *constants)
    for item in native_entries:
        assert item.provenance is not None
        if item.provenance.source_file not in source_hashes:
            raise MetadataError(f"manifest.json.source_sha256 lacks {item.provenance.source_file}")
    return RegistryEntries(
        source_revision=source_revision,
        generator_version=generator_version,
        actions=actions,
        events=events,
        expressions=expressions,
        named_constants=constants,
        source_sha256=tuple(sorted(source_hashes.items())),
        fingerprint=canonical_hash(
            {
                name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                for name in ("manifest.json", *FILE_SCHEMAS)
            }
        ),
    )
