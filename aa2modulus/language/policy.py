"""Source-language metadata layered over the shipped AAUnlimited snapshot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from ..core.source_names import is_source_name
from ..metadata.identities import WireIdentity
from ..metadata.snapshot import MetadataSnapshot
from ..model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ..model.types import TypeId
from .operators import OperatorDefinition
from .values import ActionDefault, EventValues, MemberForm, SourceValue


def _unique[T](entries: tuple[T, ...], key: Callable[[T], object]) -> tuple[T, ...]:
    result: list[T] = []
    seen: set[object] = set()
    for entry in entries:
        identifier = key(entry)
        if identifier not in seen:
            seen.add(identifier)
            result.append(entry)
    return tuple(result)


def _name_index[T](entries: tuple[tuple[T, str], ...]) -> Mapping[str, tuple[T, ...]]:
    index: dict[str, list[T]] = {}
    for target, name in entries:
        index.setdefault(name.casefold(), []).append(target)
    return MappingProxyType({name: tuple(targets) for name, targets in index.items()})


@dataclass(frozen=True, slots=True)
class LanguagePolicy:
    """Validated source syntax policy over a concrete metadata snapshot."""

    operators: tuple[OperatorDefinition, ...]
    action_defaults: tuple[ActionDefault, ...]
    action_preferred_names: tuple[tuple[int, str], ...] = ()
    expression_preferred_names: tuple[tuple[TypeId, int, str], ...] = ()
    named_constant_preferred_names: tuple[tuple[TypeId, int, str], ...] = ()
    language_version: int = field(kw_only=True)
    """Source language version, read from ``policy.toml``."""
    source_values: tuple[SourceValue, ...] = field(default=(), kw_only=True)
    readable_expressions: tuple[tuple[TypeId, int], ...] = field(default=(), kw_only=True)
    expression_defects: tuple[tuple[TypeId, int, tuple[TypeId, ...], str], ...] = field(
        default=(), kw_only=True
    )
    """(scope, id, declared parameter types, reason): native targets that cannot work."""
    expression_event_values: tuple[EventValues, ...] = field(default=(), kw_only=True)
    """Expressions whose native callback returns a value only during some events."""
    expression_result_roles: tuple[tuple[TypeId, int, str], ...] = field(default=(), kw_only=True)
    """(scope, id, role): roles of expression results; ``card`` types the result,
    others document."""
    member_forms: tuple[MemberForm, ...] = field(default=(), kw_only=True)
    protected_names: tuple[str, ...] = field(default=(), kw_only=True)
    acknowledgeable_codes: tuple[str, ...] = field(default=(), kw_only=True)
    """Hazard codes a source ``@allow(CODE)`` may acknowledge."""
    parameter_name_entries: tuple[tuple[WireIdentity, tuple[str, ...]], ...] = field(
        default=(), kw_only=True
    )
    """(target, names): documentation names of every native slot of a non-member target."""
    parameter_role_entries: tuple[tuple[WireIdentity, tuple[tuple[str, str], ...]], ...] = field(
        default=(), kw_only=True
    )
    """(target, ((parameter name, role), ...)): roles of named non-member slots."""
    description_overrides: tuple[tuple[WireIdentity, str], ...] = field(default=(), kw_only=True)
    """(target, text): maintainer wording shown instead of the native description."""

    _operator_index: Mapping[str, tuple[OperatorDefinition, ...]] = field(
        init=False, repr=False, compare=False
    )
    _default_index: Mapping[tuple[int, int], ActionDefault] = field(
        init=False, repr=False, compare=False
    )
    _action_name_index: Mapping[str, tuple[int, ...]] = field(init=False, repr=False, compare=False)
    _expression_name_index: Mapping[str, tuple[tuple[TypeId, int], ...]] = field(
        init=False, repr=False, compare=False
    )
    _constant_name_index: Mapping[str, tuple[tuple[TypeId, int], ...]] = field(
        init=False, repr=False, compare=False
    )
    _action_output_index: Mapping[int, str] = field(init=False, repr=False, compare=False)
    _expression_output_index: Mapping[tuple[TypeId, int], str] = field(
        init=False, repr=False, compare=False
    )
    _constant_output_index: Mapping[tuple[TypeId, int], str] = field(
        init=False, repr=False, compare=False
    )
    _readable_expression_index: frozenset[tuple[TypeId, int]] = field(
        init=False, repr=False, compare=False
    )
    _result_role_index: Mapping[tuple[TypeId, int], str] = field(
        init=False, repr=False, compare=False
    )
    _defect_index: Mapping[tuple[TypeId, int], str] = field(init=False, repr=False, compare=False)
    _event_value_index: Mapping[WireIdentity, EventValues] = field(
        init=False, repr=False, compare=False
    )
    _parameter_name_index: Mapping[WireIdentity, tuple[str, ...]] = field(
        init=False, repr=False, compare=False
    )
    _parameter_role_index: Mapping[WireIdentity, tuple[str | None, ...]] = field(
        init=False, repr=False, compare=False
    )
    _description_index: Mapping[WireIdentity, str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._check_spellings()
        self._index_names()
        self._index_targets()

    def _check_spellings(self) -> None:
        """Preferred names are source names, one per target."""

        preferred_groups = (
            ("actions", (name for _, name in self.action_preferred_names)),
            ("expressions", (name for _, _, name in self.expression_preferred_names)),
            ("named_constants", (name for _, _, name in self.named_constant_preferred_names)),
        )
        for kind, names in preferred_groups:
            if any(not is_source_name(name) for name in names):
                raise ValueError(f"{kind} preferred names must be exact non-keyword source names")
        preferred_targets = (
            ("actions", tuple(target for target, _ in self.action_preferred_names)),
            (
                "expressions",
                tuple(
                    (scope, identifier) for scope, identifier, _ in self.expression_preferred_names
                ),
            ),
            (
                "named_constants",
                tuple(
                    (scope, identifier)
                    for scope, identifier, _ in self.named_constant_preferred_names
                ),
            ),
        )
        for kind, targets in preferred_targets:
            if len(set(targets)) != len(targets):
                raise ValueError(f"{kind} preferred names must assign one name per target")

    def _index_names(self) -> None:
        """Operator, default, spelling and output-name lookups."""

        operators: dict[str, list[OperatorDefinition]] = {}
        for operator in self.operators:
            operators.setdefault(operator.token, []).append(operator)
        object.__setattr__(
            self, "_operator_index", MappingProxyType({k: tuple(v) for k, v in operators.items()})
        )
        object.__setattr__(
            self,
            "_default_index",
            MappingProxyType({(d.action_id, d.parameter_index): d for d in self.action_defaults}),
        )
        expression_names = tuple(
            ((scope, identifier), name)
            for scope, identifier, name in self.expression_preferred_names
        )
        constant_names = tuple(
            ((scope, identifier), name)
            for scope, identifier, name in self.named_constant_preferred_names
        )
        object.__setattr__(self, "_action_name_index", _name_index(self.action_preferred_names))
        object.__setattr__(self, "_expression_name_index", _name_index(expression_names))
        object.__setattr__(self, "_constant_name_index", _name_index(constant_names))
        object.__setattr__(
            self, "_action_output_index", MappingProxyType(dict(self.action_preferred_names))
        )
        object.__setattr__(
            self,
            "_expression_output_index",
            MappingProxyType(
                {
                    (scope, identifier): name
                    for scope, identifier, name in self.expression_preferred_names
                }
            ),
        )
        object.__setattr__(
            self,
            "_constant_output_index",
            MappingProxyType(
                {
                    (scope, identifier): name
                    for scope, identifier, name in self.named_constant_preferred_names
                }
            ),
        )

    def _index_targets(self) -> None:
        """Per-target readability, defects, event values, roles and documentation."""

        object.__setattr__(self, "_readable_expression_index", frozenset(self.readable_expressions))
        object.__setattr__(
            self,
            "_defect_index",
            MappingProxyType(
                {
                    (scope, identifier): reason
                    for scope, identifier, _declared, reason in self.expression_defects
                }
            ),
        )
        object.__setattr__(
            self,
            "_event_value_index",
            MappingProxyType({item.target: item for item in self.expression_event_values}),
        )
        object.__setattr__(
            self,
            "_result_role_index",
            MappingProxyType(
                {
                    (scope, identifier): role
                    for scope, identifier, role in self.expression_result_roles
                }
            ),
        )
        object.__setattr__(
            self, "_parameter_name_index", MappingProxyType(dict(self.parameter_name_entries))
        )
        role_index: dict[WireIdentity, tuple[str | None, ...]] = {}
        for target, roles in self.parameter_role_entries:
            slots = self._parameter_name_index.get(target, ())
            by_name = dict(roles)
            role_index[target] = tuple(by_name.get(slot) for slot in slots)
        object.__setattr__(self, "_parameter_role_index", MappingProxyType(role_index))
        object.__setattr__(
            self, "_description_index", MappingProxyType(dict(self.description_overrides))
        )

    def operator_candidates(
        self,
        token: str,
        parameter_types: tuple[TypeId, ...] | None = None,
        *,
        return_type: TypeId | None = None,
    ) -> tuple[OperatorDefinition, ...]:
        return tuple(
            item
            for item in self._operator_index.get(token, ())
            if (parameter_types is None or item.parameter_types == parameter_types)
            and (return_type is None or item.return_type == return_type)
        )

    def member_form_candidates(
        self,
        member: str,
        *,
        kind: Literal["action", "expression"] | None = None,
        arguments: int | None = None,
    ) -> tuple[MemberForm, ...]:
        """Return configured receiver forms by exact member spelling (case-insensitive)."""

        return tuple(
            form
            for form in self.member_forms
            if form.name.casefold() == member.casefold()
            and (kind is None or form.target.kind == kind)
            and (arguments is None or len(form.arguments) == arguments)
        )

    def member_form_for_target(self, target: WireIdentity) -> MemberForm | None:
        """Return the receiver form that is this native target's canonical spelling, if any."""

        return next((form for form in self.member_forms if form.target == target), None)

    def namespace_roots(self) -> frozenset[str]:
        """First segments (exact case) of every configured qualified source name."""

        names: list[str] = [item.name for item in self.source_values]
        names.extend(name for _, name in self.action_preferred_names)
        names.extend(name for _, _, name in self.expression_preferred_names)
        names.extend(name for _, _, name in self.named_constant_preferred_names)
        return frozenset(name.split(".", 1)[0] for name in names if "." in name)

    def action_default(self, action_id: int, parameter_index: int) -> ActionDefault | None:
        return self._default_index.get((action_id, parameter_index))

    def is_expression_readable(self, return_type: TypeId, expression_id: int) -> bool:
        """Whether policy opts this expression into readable output despite a native anomaly."""

        return (return_type, expression_id) in self._readable_expression_index

    def expression_defect(self, return_type: TypeId, expression_id: int) -> str | None:
        """Why policy rejects every use of this expression as natively unusable."""

        return self._defect_index.get((return_type, expression_id))

    def event_values(self, target: WireIdentity) -> EventValues | None:
        """When the expression's native callback returns a value only during some events."""

        return self._event_value_index.get(target)

    def expression_result_role(self, return_type: TypeId, expression_id: int) -> str | None:
        """The role of an expression's result (``card`` types it as a source card), if any."""

        return self._result_role_index.get((return_type, expression_id))

    def parameter_names(self, target: WireIdentity) -> tuple[str, ...] | None:
        """Documentation names of every native slot of a non-member target, if configured.

        Member targets name their explicit arguments in ``[members]`` instead.
        """

        return self._parameter_name_index.get(target)

    def parameter_roles(self, target: WireIdentity) -> tuple[str | None, ...] | None:
        """Per-slot roles of a non-member target (``None`` for an untagged slot), if any.

        Role ``card`` types the slot as a source ``card``; other roles document.
        """

        return self._parameter_role_index.get(target)

    def description_override(self, target: WireIdentity) -> str | None:
        """Maintainer wording that replaces the native description, if configured."""

        return self._description_index.get(target)

    def preferred_action_name(self, action_id: int) -> str | None:
        return self._action_output_index.get(action_id)

    def preferred_expression_name(self, return_type: TypeId, identifier: int) -> str | None:
        return self._expression_output_index.get((return_type, identifier))

    def preferred_named_constant_name(self, value_type: TypeId, identifier: int) -> str | None:
        return self._constant_output_index.get((value_type, identifier))

    def action_candidates(
        self, metadata: MetadataSnapshot, name: str
    ) -> tuple[ActionMetadata, ...]:
        key = name.casefold()
        if key in self._action_name_index:
            candidates = tuple(
                entry
                for identifier in dict.fromkeys(self._action_name_index[key])
                if (entry := metadata.action(identifier)) is not None
            )
        else:
            candidates = ()
        candidates += metadata.action_candidates_by_name(name)
        return _unique(candidates, lambda e: e.id)

    def event_candidates(self, metadata: MetadataSnapshot, name: str) -> tuple[EventMetadata, ...]:
        # Events have no preferred names; they keep their native spellings.
        return _unique(metadata.event_candidates_by_name(name), lambda e: e.id)

    def expression_candidates(
        self, metadata: MetadataSnapshot, name: str
    ) -> tuple[ExpressionMetadata, ...]:
        key = name.casefold()
        if key in self._expression_name_index:
            candidates = tuple(
                entry
                for scope, identifier in dict.fromkeys(self._expression_name_index[key])
                if (entry := metadata.expression(scope, identifier)) is not None
            )
        else:
            candidates = ()
        candidates += metadata.expression_candidates_by_name(name)
        return _unique(candidates, lambda e: (e.return_type, e.id))

    def named_constant_candidates(
        self,
        metadata: MetadataSnapshot,
        name: str,
        value_type: TypeId | None = None,
    ) -> tuple[NamedConstantMetadata, ...]:
        key = name.casefold()
        if key in self._constant_name_index:
            candidates: list[NamedConstantMetadata] = []
            for scope, identifier in dict.fromkeys(self._constant_name_index[key]):
                if value_type is not None and value_type != scope:
                    continue
                # Keep every row with this explicit ID, even when names differ.
                # The native first-match lookup is separate from source ambiguity.
                candidates.extend(metadata.named_constant_candidates(scope, identifier))
        else:
            candidates = []
        candidates.extend(metadata.named_constant_candidates_by_name(name, value_type))
        selected: list[NamedConstantMetadata] = []
        for entry in candidates:
            winner = metadata.named_constant(entry.value_type, entry.id)
            if winner is None or winner.id != entry.id:
                continue
            if entry.resolved_value is not None and winner.resolved_value is not None:
                equivalent = entry.resolved_value == winner.resolved_value
            else:
                equivalent = (
                    entry.value == winner.value
                    and entry.value_expression == winner.value_expression
                )
            if equivalent:
                selected.append(winner)
        return _unique(tuple(selected), lambda entry: (entry.value_type, entry.id))
