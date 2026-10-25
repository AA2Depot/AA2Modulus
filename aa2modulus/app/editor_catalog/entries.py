"""Editor entries: one per source-spelled native row, with signature and description"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...context.operation import SourceContext
from ...language.catalog.names import source_names
from ...language.documentation import builtin_anchor, builtin_description, constant_ordinals
from ...metadata.identities import native_key
from ...model.display import type_name, value_text
from ...model.native import (
    ActionMetadata,
    EventMetadata,
    ExpressionMetadata,
    NamedConstantMetadata,
)
from ...model.types import ValueType

DEFAULT_EVENT = "CARD_ADDED"
PLACEHOLDERS = {
    ValueType.INT: "0",
    ValueType.BOOL: "true",
    ValueType.FLOAT: "1.0",
    ValueType.STRING: '"text"',
}


class NoExample(Exception):
    """The entry has no natural call form to demonstrate."""


@dataclass(slots=True)
class Report:
    counts: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    missing_names: list[str] = field(default_factory=list)
    omitted_examples: list[tuple[str, str]] = field(default_factory=list)

    def lines(self) -> list[str]:
        lines = ["entries: " + ", ".join(f"{k}={v}" for k, v in sorted(self.counts.items()))]

        lines.append(f"skipped (no canonical source spelling): {len(self.skipped)}")
        lines += [f"  {item}" for item in self.skipped]

        lines.append(f"targets without policy parameter names: {len(self.missing_names)}")
        lines += [f"  {item}" for item in self.missing_names]

        lines.append(f"omitted examples: {len(self.omitted_examples)}")
        lines += [f"  {key}: {reason}" for key, reason in self.omitted_examples]

        return lines


@dataclass(slots=True)
class Draft:
    entry: dict[str, Any]
    event: str
    body: str | None  # trigger body demonstrating the entry; None when there is none
    note: str | None = None  # why there is no body


def build(context: SourceContext, report: Report) -> list[Draft]:
    builder = _Builder(context, report)
    snapshot = builder.snapshot

    for action in sorted(snapshot.actions, key=lambda item: item.id):
        builder.callable(action)
    for event in sorted(snapshot.events, key=lambda item: item.id):
        builder.event(event)
    for expression in sorted(
        snapshot.expressions, key=lambda item: (int(item.return_type), item.id)
    ):
        builder.callable(expression)
    builder.constants()

    for draft in builder.drafts:
        kind = draft.entry["kind"]
        report.counts[kind] = report.counts.get(kind, 0) + 1

    return builder.drafts


class _Builder:
    def __init__(self, context: SourceContext, report: Report):
        self.snapshot = context.metadata
        self.policy = context.source_policy
        self.catalog = context.catalog
        self.report = report
        self.drafts: list[Draft] = []
        self.seen: set[str] = set()

        self.operators = {
            (item.return_type, item.expression_id): item.token for item in self.policy.operators
        }
        self.event_names: dict[int, str] = {}
        for event in self.snapshot.events:
            names = self.names(event)
            if spelling := names["preferred"] or next(iter(names["candidates"]), None):
                self.event_names[event.id] = spelling

    def names(self, entry: Any) -> dict[str, Any]:
        return source_names(entry, self.catalog)

    def add(
        self,
        native: Any,
        anchor: str,
        names: dict[str, Any],
        kind: str,
        signature: dict[str, Any],
        *,
        body: str | None,
        event: str = DEFAULT_EVENT,
        value_events: list[str] | None = None,
        note: str | None = None,
    ) -> None:
        if anchor in self.seen:
            raise ValueError(f"duplicate entry id {anchor}")
        self.seen.add(anchor)

        name = _name(names)
        entry = {
            "id": anchor,
            "kind": kind,
            "name": name,
            "nativeName": native.name,
            "aliases": [item for item in names["candidates"] if item != name],
            "category": getattr(native, "category", None),
            "description": builtin_description(self.policy, native),
            "signatures": [signature],
            "valueEvents": value_events,
            "example": None,
            "docPath": f"builtins/{anchor}",
        }
        self.drafts.append(Draft(entry, value_events[0] if value_events else event, body, note))

    def callable(self, native: ActionMetadata | ExpressionMetadata) -> None:
        """Add the entry for an action or expression, or record why it is skipped."""

        anchor = builtin_anchor(native)
        names = self.names(native)
        if not names["preferred"]:
            self.report.skipped.append(f"{anchor} ({native.name}): no canonical source spelling")
            return

        name = _name(names)
        wire = native_key(native)
        form = self.policy.member_form_for_target(wire)
        expression = isinstance(native, ExpressionMetadata)
        wire_type = native.return_type if isinstance(native, ExpressionMetadata) else None
        return_type = wire_type
        result_role = (
            self.policy.expression_result_role(native.return_type, native.id)
            if isinstance(native, ExpressionMetadata)
            else None
        )

        # A member target's only spelling is its member form: <card>.AddLike(...).
        receiver = None
        parameters: list[dict[str, Any]] = []
        arguments: list[str] = []
        try:
            if form is not None:
                receiver = {"role": form.receiver_role, "type": type_name(form.receiver_type)}
                receiver_placeholder = _placeholder(
                    form.receiver_type, form.receiver_role, receiver=True
                )
                use = f"{receiver_placeholder}.{form.name}"
                for item, type_id in zip(form.arguments, form.argument_types, strict=True):
                    default = self.default(native, item.parameter)
                    parameters.append(_parameter(item.name, type_id, item.role, default))
                    arguments.append(default or _placeholder(type_id, item.role))
                if form.result_type is not None:
                    return_type = form.result_type
                bare = expression and not form.arguments
            else:
                flat = self.policy.parameter_names(wire)
                roles = self.policy.parameter_roles(wire) or (None,) * len(native.parameter_types)
                if flat is None and native.parameter_types:
                    self.report.missing_names.append(
                        f"{anchor} {names['preferred'] or native.name}"
                    )
                for index, type_id in enumerate(native.parameter_types):
                    default = self.default(native, index)
                    parameter = flat[index] if flat else f"arg{index + 1}"
                    parameters.append(_parameter(parameter, type_id, roles[index], default))
                    arguments.append(default or _placeholder(type_id, roles[index]))
                use = name
                bare = expression and not native.parameter_types

            label = name if bare else f"{name}({_join(parameters)})"
            body = _statement(native, wire_type, use if bare else f"{use}({', '.join(arguments)})")
            note = None
        except NoExample as error:
            label = f"{name}({_join(parameters)})"
            body, note = None, str(error)

        if return_type is not None:
            label += f" -> {_type_text(type_name(return_type), result_role)}"

        value_events = None
        target = self.catalog.native_targets[wire]
        if isinstance(native, ExpressionMetadata) and target.event_values is not None:
            ids = target.event_values.field_events(native.return_type)
            value_events = [self.event_names[i] for i in ids if i in self.event_names] or None

        signature = {
            "label": label,
            "receiver": receiver,
            "parameters": parameters,
            "returns": None
            if return_type is None
            else {"type": type_name(return_type), "role": result_role},
            "operator": self.operators.get((native.return_type, native.id))
            if isinstance(native, ExpressionMetadata)
            else None,
        }
        kind = "expression" if expression else "action"
        self.add(
            native, anchor, names, kind, signature, body=body, value_events=value_events, note=note
        )

    def event(self, native: EventMetadata) -> None:
        names = self.names(native)
        if not names["preferred"]:
            self.report.skipped.append(
                f"event-{native.id} ({native.name}): no canonical source spelling"
            )
            return

        # The example is an empty trigger on the event itself.
        name = _name(names)
        self.add(
            native,
            builtin_anchor(native),
            names,
            "event",
            _plain(f"on {name}"),
            body="",
            event=name,
        )

    def constants(self) -> None:
        rows: dict[str, NamedConstantMetadata] = {}

        for native, ordinal in constant_ordinals(self.snapshot.named_constants):
            anchor = builtin_anchor(native, ordinal=ordinal)
            rows[anchor] = native

            # Shadowed rows are documented through their literal source value below.
            names = self.names(native)
            if not names["preferred"]:
                continue

            name = _name(names)
            value = native.resolved_value or native.value
            label = f"{name}: {type_name(native.value_type)}"
            if value is not None:
                label += f" = {value_text(value)}"
            body = _statement(native, native.value_type, name)
            self.add(native, anchor, names, "named_constant", _plain(label), body=body)

        for literal in self.catalog.source_values:
            anchor = builtin_anchor(literal)
            row = rows.get(anchor)
            if row is None or anchor in self.seen:
                continue

            names = {"preferred": literal.name, "candidates": [literal.name]}
            label = f"{literal.name}: {type_name(literal.value_type)} = {value_text(literal.value)}"
            body = _statement(row, literal.value_type, literal.name)
            self.add(row, anchor, names, "named_constant", _plain(label), body=body)

    def default(self, native: Any, index: int) -> str | None:
        if not isinstance(native, ActionMetadata):
            return None
        default = self.policy.action_default(native.id, index)
        return None if default is None else str(value_text(default.value))


def _name(names: dict[str, Any]) -> str:
    candidates: list[str] = names["candidates"]
    return str(names["preferred"] if names["preferred"] in candidates else candidates[0])


def _plain(label: str) -> dict[str, Any]:
    """Signature of an entry with no receiver, parameters or result."""

    return {"label": label, "receiver": None, "parameters": [], "returns": None, "operator": None}


def _parameter(name: str, type_id: int, role: str | None, default: str | None) -> dict[str, Any]:
    return {"name": name, "type": type_name(type_id), "role": role, "default": default}


def _placeholder(type_id: int, role: str | None, *, receiver: bool = False) -> str:
    if role == "card":
        return "ThisCard" if receiver else "TriggeringCard"
    try:
        return PLACEHOLDERS[ValueType(type_id)]
    except KeyError:
        raise NoExample(f"no placeholder for type {type_name(type_id)}") from None


def _statement(native: Any, value_type: int | None, use: str) -> str:
    """An action call, or a value used where its wire type fits."""

    if isinstance(native, ActionMetadata):
        return f"{use};"
    if value_type == ValueType.BOOL:
        return f"if ({use}) {{ }}"
    assert value_type is not None
    return f"let value: {type_name(value_type)} = {use};"


def _type_text(kind: str, role: str | None) -> str:
    """A card-role ``int`` is written ``card`` in source."""

    return "card" if role == "card" and kind == "int" else kind


def _join(parameters: list[dict[str, Any]]) -> str:
    return ", ".join(
        f"{item['name']}: {_type_text(item['type'], item['role'])}"
        + (f" = {item['default']}" if item["default"] else "")
        for item in parameters
    )
