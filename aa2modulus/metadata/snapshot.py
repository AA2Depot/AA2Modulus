"""The indexed, runtime-ready registry snapshot."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from ..core.source_names import is_source_name, source_identifier
from ..model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ..model.records import ActionCall, Event, Expression, GuiAction, Module, Trigger, Variable
from ..model.types import EXPR_PAYLOAD_MARKERS, TypeId, ValueType
from .fingerprint import canonical_hash, input_data
from .registry import RegistryEntries
from .schema import MetadataError


def _metadata_aliases[
    T: ActionMetadata | EventMetadata | ExpressionMetadata | NamedConstantMetadata
](
    entries: tuple[T, ...],
    *,
    include_payload_markers: bool = True,
) -> dict[str, tuple[T, ...]]:
    index: dict[str, list[T]] = {}
    for entry in entries:
        if not include_payload_markers and entry.id in EXPR_PAYLOAD_MARKERS:
            continue
        names = {
            entry.name.casefold(),
            source_identifier(entry.name).casefold(),
        }
        if is_source_name(entry.interactive_name):
            names.add(entry.interactive_name.casefold())
        symbol = getattr(entry, "symbol", None)
        if symbol:
            names.add(symbol.casefold())
        for name in names:
            if name:
                index.setdefault(name, []).append(entry)
    return {name: tuple(items) for name, items in index.items()}


@dataclass(frozen=True, slots=True)
class MetadataSnapshot:
    """Validated, runtime-ready metadata mappings."""

    source_revision: str
    generator_version: str
    actions: tuple[ActionMetadata, ...]
    events: tuple[EventMetadata, ...]
    expressions: tuple[ExpressionMetadata, ...]
    named_constants: tuple[NamedConstantMetadata, ...]
    source_sha256: Mapping[str, str]
    _resource_fingerprint: str
    fingerprint: str = field(init=False)
    _actions_by_id: Mapping[int, ActionMetadata]
    _events_by_id: Mapping[int, EventMetadata]
    _expressions_by_scope: Mapping[tuple[int | ValueType, int], ExpressionMetadata]
    _named_constants_by_scope: Mapping[int | ValueType, tuple[NamedConstantMetadata, ...]]
    _actions_by_name: Mapping[str, tuple[ActionMetadata, ...]]
    _events_by_name: Mapping[str, tuple[EventMetadata, ...]]
    _expressions_by_name: Mapping[str, tuple[ExpressionMetadata, ...]]
    _named_constants_by_name: Mapping[str, tuple[NamedConstantMetadata, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_sha256", MappingProxyType(dict(self.source_sha256)))
        object.__setattr__(
            self,
            "fingerprint",
            canonical_hash(
                {
                    "resources": self._resource_fingerprint,
                    "source_revision": self.source_revision,
                    "generator_version": self.generator_version,
                    "source_sha256": input_data(self.source_sha256),
                    "actions": input_data(self.actions),
                    "events": input_data(self.events),
                    "expressions": input_data(self.expressions),
                    "named_constants": input_data(self.named_constants),
                }
            ),
        )

    def action(self, identifier: int) -> ActionMetadata | None:
        return self._actions_by_id.get(identifier)

    def action_candidates_by_name(self, name: str) -> tuple[ActionMetadata, ...]:
        return self._actions_by_name.get(name.casefold(), ())

    def event(self, identifier: int) -> EventMetadata | None:
        return self._events_by_id.get(identifier)

    def event_candidates_by_name(self, name: str) -> tuple[EventMetadata, ...]:
        return self._events_by_name.get(name.casefold(), ())

    def expression_candidates_by_name(self, name: str) -> tuple[ExpressionMetadata, ...]:
        return self._expressions_by_name.get(name.casefold(), ())

    def named_constant_by_name(
        self,
        value_type: int | ValueType,
        name: str,
    ) -> NamedConstantMetadata | None:
        candidates = self.named_constant_candidates_by_name(name, value_type)
        return candidates[0] if len(candidates) == 1 else None

    def named_constant_candidates_by_name(
        self,
        name: str,
        value_type: TypeId | None = None,
    ) -> tuple[NamedConstantMetadata, ...]:
        candidates = self._named_constants_by_name.get(name.casefold(), ())
        if value_type is None:
            return candidates
        return tuple(item for item in candidates if item.value_type == value_type)

    def expression(
        self, return_type: int | ValueType, identifier: int
    ) -> ExpressionMetadata | None:
        return self._expressions_by_scope.get((return_type, identifier))

    def named_constant(
        self, value_type: int | ValueType, identifier: int
    ) -> NamedConstantMetadata | None:
        entries = self._named_constants_by_scope.get(value_type, ())
        for entry in entries:
            if entry.id == identifier:
                return entry
        if 1 <= identifier <= len(entries):
            return entries[identifier - 1]
        return None

    def named_constant_candidates(
        self, value_type: TypeId, identifier: int
    ) -> tuple[NamedConstantMetadata, ...]:
        """Return every explicit-ID record in registry order, without fallback."""

        return tuple(
            entry
            for entry in self._named_constants_by_scope.get(value_type, ())
            if entry.id == identifier
        )

    def resolve_module(self, module: Module) -> Module:
        """Return a metadata-annotated copy while preserving diagnostics."""

        def resolve_expression(expression: Expression) -> Expression:
            named_constant = expression.named_constant
            if named_constant is not None:
                named_metadata = self.named_constant(named_constant.value_type, named_constant.id)
                # Positional lookup can resolve a different explicit ID. Keep
                # that API behavior without annotating the serialized reference
                # with metadata that violates its identity invariant.
                if named_metadata is not None and named_metadata.id != named_constant.id:
                    named_metadata = None
                named_constant = replace(
                    named_constant,
                    metadata=named_metadata,
                )
            parameters = tuple(resolve_expression(item) for item in expression.parameters)
            return replace(
                expression,
                named_constant=named_constant,
                parameters=parameters,
                metadata=self.expression(expression.return_type, expression.id),
            )

        def resolve_event(event: Event) -> Event:
            return replace(
                event,
                parameters=tuple(resolve_expression(item) for item in event.parameters),
                metadata=self.event(event.id),
            )

        def resolve_action(action: ActionCall) -> ActionCall:
            return replace(
                action,
                parameters=tuple(resolve_expression(item) for item in action.parameters),
                metadata=self.action(action.id),
            )

        def resolve_gui_action(action: GuiAction) -> GuiAction:
            return replace(
                action,
                action=resolve_action(action.action),
                children=tuple(resolve_gui_action(child) for child in action.children),
            )

        def resolve_variable(variable: Variable) -> Variable:
            return replace(
                variable, default_expression=resolve_expression(variable.default_expression)
            )

        def resolve_trigger(trigger: Trigger) -> Trigger:
            return replace(
                trigger,
                events=tuple(resolve_event(item) for item in trigger.events),
                variables=tuple(resolve_variable(item) for item in trigger.variables),
                gui_actions=tuple(resolve_gui_action(item) for item in trigger.gui_actions),
            )

        return replace(
            module,
            triggers=tuple(resolve_trigger(item) for item in module.triggers),
        )


def index_snapshot(entries: RegistryEntries) -> MetadataSnapshot:
    actions = entries.actions
    events = entries.events
    expressions = entries.expressions
    named_constants = entries.named_constants
    named_scopes: dict[TypeId, list[NamedConstantMetadata]] = {}
    for constant in named_constants:
        named_scopes.setdefault(constant.value_type, []).append(constant)
    action_map: dict[int, ActionMetadata] = {}
    for action_item in actions:
        if action_item.id in action_map:
            raise MetadataError(f"duplicate action id {action_item.id}")
        action_map[action_item.id] = action_item
    event_map: dict[int, EventMetadata] = {}
    for event_item in events:
        if event_item.id in event_map:
            raise MetadataError(f"duplicate event id {event_item.id}")
        event_map[event_item.id] = event_item
    expression_map: dict[tuple[int | ValueType, int], ExpressionMetadata] = {}
    for expression_item in expressions:
        key = (expression_item.return_type, expression_item.id)
        if key in expression_map:
            raise MetadataError(f"duplicate expression scope {key!r}")
        expression_map[key] = expression_item

    action_aliases = _metadata_aliases(tuple(actions))
    event_aliases = _metadata_aliases(tuple(events))
    expression_aliases = _metadata_aliases(tuple(expressions), include_payload_markers=False)
    named_constant_aliases = _metadata_aliases(tuple(named_constants))
    return MetadataSnapshot(
        source_revision=entries.source_revision,
        generator_version=entries.generator_version,
        actions=actions,
        events=events,
        expressions=expressions,
        named_constants=named_constants,
        source_sha256=MappingProxyType(dict(entries.source_sha256)),
        _resource_fingerprint=entries.fingerprint,
        _actions_by_id=MappingProxyType(action_map),
        _events_by_id=MappingProxyType(event_map),
        _expressions_by_scope=MappingProxyType(expression_map),
        _named_constants_by_scope=MappingProxyType(
            {key: tuple(value) for key, value in named_scopes.items()}
        ),
        _actions_by_name=MappingProxyType(action_aliases),
        _events_by_name=MappingProxyType(event_aliases),
        _expressions_by_name=MappingProxyType(expression_aliases),
        _named_constants_by_name=MappingProxyType(named_constant_aliases),
    )
