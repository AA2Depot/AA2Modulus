"""Expressions whose native value depends on the event or on how AAUnlimited saves them."""

from __future__ import annotations

from ...language.values import EventValues
from ...metadata.identities import WireIdentity
from ...model.display import type_name
from ...model.records import Expression
from ...model.types import TypeId, ValueType
from .labels import or_list, value_text, with_article
from .state import ValidatorState


def validate_reviewed_expression(
    state: ValidatorState, expression: Expression, path: tuple[str | int, ...]
) -> None:
    """Apply catalog-backed native claims in the current event context."""

    if state.catalog is None:
        return
    target = state.catalog.native_targets.get(
        WireIdentity("expression", expression.id, expression.return_type)
    )
    if target is None:
        return
    if target.event_values is not None:
        validate_event_values(state, expression, path, target.event_values)
    if target.save_identity != target.wire:
        source_scope = target.wire.scope
        saved_scope = target.save_identity.scope
        assert source_scope is not None and saved_scope is not None
        state.reporter.add(
            expression,
            path,
            "NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE",
            f"{state.labels.expression(expression)} is "
            f"{with_article(type_name(source_scope))} here, but AAUnlimited saves it as "
            f"{with_article(type_name(saved_scope))}, so it can change type when the "
            "module is saved and reloaded",
            severity="warning",
            field_path=("return_type",),
        )


def validate_event_values(
    state: ValidatorState, expression: Expression, path: tuple[str | int, ...], values: EventValues
) -> None:
    """Check the value type the native callback returns in each of the trigger's events."""

    event_ids = state.trigger_event_ids
    known_ids = tuple(
        identifier
        for identifier in (event_ids or ())
        if state.metadata.event(identifier) is not None
    )
    unknown_context = not known_ids or (event_ids is not None and len(known_ids) != len(event_ids))
    if unknown_context:
        state.reporter.add(
            expression,
            path,
            "REVIEWED_VALUE_CONTEXT_UNKNOWN",
            f"{state.labels.expression(expression)} "
            f"{value_events_text(state, values, expression.return_type)}, but "
            "this trigger has no fully known event, so its runtime type is unknown",
            severity="warning",
            field_path=("id",),
        )
    for event_id in known_ids:
        if values.value_type(event_id) != expression.return_type:
            state.reporter.add(
                expression,
                path,
                "REVIEWED_VALUE_TYPE_MISMATCH",
                reviewed_mismatch_message(state, expression, values, event_id),
                severity="warning" if state.native else "error",
                field_path=("return_type",),
            )


def value_events_text(state: ValidatorState, values: EventValues, value_type: TypeId) -> str:
    """``only reads an int from event data during A or B``, else ``reads event data``."""

    events = values.field_events(value_type)
    if not events:
        return "reads event data"
    return (
        f"only reads {with_article(type_name(value_type))} from event data during "
        f"{or_list([state.labels.event(event_id) for event_id in events])}"
    )


def reviewed_mismatch_message(
    state: ValidatorState, expression: Expression, values: EventValues, event_id: int
) -> str:
    """Say what AAUnlimited returns in this event and why the read is unreliable.

    The evaluator passes the callback's ``Value`` on without a type check, and a
    bool ``Value`` writes one byte of its union, so wider reads see leftover bits.
    """

    label = state.labels.expression(expression)
    event = state.labels.event(event_id)
    expected = with_article(type_name(expression.return_type))
    actual = values.value_type(event_id)
    if actual == ValueType.BOOL and expression.return_type in (
        ValueType.INT,
        ValueType.FLOAT,
    ):
        consequence = "so this reads unspecified bits that can change between reads"
    else:
        consequence = "and the value is read without conversion"
    literal = values.literal(event_id)
    if literal is not None:
        return (
            f"{label} {value_events_text(state, values, expression.return_type)}; "
            f"during {event} AAUnlimited returns `{value_text(literal)}` "
            f"instead of {expected}, {consequence}"
        )
    return (
        f"during {event}, {label} returns {with_article(type_name(actual))} "
        f"field instead of {expected}, {consequence}"
    )
