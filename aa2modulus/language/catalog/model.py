"""Catalog records: native targets, their source forms and constant rows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, cast

from ...metadata.identities import NativeKind, NativeMetadata, RowIdentity, WireIdentity
from ...metadata.snapshot import MetadataSnapshot
from ...model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ...model.types import TypeId
from ...model.values import Value
from ..policy import LanguagePolicy
from ..values import EventValues, MemberForm, SourceValue

FormKind = Literal["call", "getter", "constant", "operator", "keyword", "member"]
"""``member`` is a card-first target's only form: ``receiver.Name(...)`` or ``receiver.Name``."""


@dataclass(frozen=True, slots=True)
class SemanticSignature:
    parameter_types: tuple[TypeId, ...]
    result_type: TypeId | None
    defaults: tuple[tuple[int, Value], ...] = ()


@dataclass(frozen=True, slots=True)
class SourceForm:
    key: str
    spelling: str
    kind: FormKind
    target: WireIdentity
    signature: SemanticSignature
    parameter_order: tuple[int, ...]
    reversible: bool
    canonical: bool = False
    reason: str | None = None
    member: MemberForm | None = None
    """The receiver projection when ``kind`` is ``member``; ``spelling`` is its member name."""


@dataclass(frozen=True, slots=True)
class NativeTarget:
    wire: WireIdentity
    row: RowIdentity
    metadata: NativeMetadata
    signature: SemanticSignature
    declared_return_type: TypeId | None
    save_identity: WireIdentity
    reload_row: RowIdentity | None
    documentation_key: str
    event_values: EventValues | None = None
    forms: tuple[SourceForm, ...] = ()
    source_reason: str | None = None

    @property
    def canonical_form(self) -> SourceForm | None:
        return next((form for form in self.forms if form.canonical), None)


@dataclass(frozen=True, slots=True)
class ConstantRow:
    identity: RowIdentity
    metadata: NamedConstantMetadata
    explicit_lookup: RowIdentity
    status: Literal["first_row", "equivalent_duplicate", "shadowed_value", "unverified_value"]
    selecting_wire_ids: tuple[int, ...]
    documentation_key: str


@dataclass(frozen=True, slots=True)
class LanguageCatalog:
    metadata: MetadataSnapshot
    policy: LanguagePolicy
    native_targets: Mapping[WireIdentity, NativeTarget]
    constant_rows: tuple[ConstantRow, ...]
    source_forms: Mapping[str, SourceForm]
    fingerprint: str
    _names: Mapping[tuple[NativeKind, str], tuple[WireIdentity, ...]]
    _rejected_names: Mapping[tuple[str, TypeId], tuple[str, str]]
    _retired_names: Mapping[tuple[NativeKind, str], tuple[str, ...]] = MappingProxyType({})
    """(kind, casefolded spelling) -> canonical names, for native spellings no longer accepted."""
    _retired_members: Mapping[tuple[NativeKind, str], tuple[MemberForm, ...]] = MappingProxyType({})
    """(kind, casefolded flat spelling) -> member forms of the card-first targets that retire it."""
    namespace_roots: frozenset[str] = field(init=False)
    """Exact-case roots of registered qualified source names (static namespaces)."""
    _folded_roots: Mapping[str, str] = field(init=False, repr=False, compare=False)
    protected_names: frozenset[str] = field(init=False)
    """Casefolded built-in names that source can never shadow or redeclare."""

    def __post_init__(self) -> None:
        roots = self.policy.namespace_roots() | frozenset(
            form.spelling.split(".", 1)[0]
            for form in self.source_forms.values()
            if "." in form.spelling
        )
        folded = {root.casefold(): root for root in sorted(roots, reverse=True)}
        object.__setattr__(self, "namespace_roots", roots)
        object.__setattr__(
            self,
            "protected_names",
            frozenset(name.casefold() for name in self.policy.protected_names),
        )
        object.__setattr__(self, "_folded_roots", MappingProxyType(folded))

    @property
    def source_values(self) -> tuple[SourceValue, ...]:
        return self.policy.source_values

    def source_value(self, name: str, value_type: TypeId | None = None) -> SourceValue | None:
        if self.root_case_variant(name) is not None:
            return None
        return next(
            (
                item
                for item in self.source_values
                if item.name.casefold() == name.casefold()
                and (value_type is None or item.value_type == value_type)
            ),
            None,
        )

    def rejected_constant_name(
        self, name: str, value_type: TypeId | None = None
    ) -> tuple[str, str] | None:
        """The (problem, help) text for a shadowed native constant alias, if rejected."""

        if self.root_case_variant(name) is not None:
            return None
        return next(
            (
                reason
                for (spelling, scope), reason in self._rejected_names.items()
                if spelling == name.casefold() and (value_type is None or scope == value_type)
            ),
            None,
        )

    def retired_names(self, name: str, *kinds: NativeKind) -> tuple[str, ...]:
        """Canonical names for a native spelling that a canonical-named target rejects.

        Empty when the spelling is still accepted for that kind, or for the lookup-only
        provider, which cannot enumerate canonical forms.
        """

        folded = name.casefold()
        found: list[str] = []
        for kind in kinds:
            if (kind, folded) in self._names:
                continue
            found.extend(self._retired_names.get((kind, folded), ()))
        return tuple(dict.fromkeys(found))

    def retired_member_forms(
        self, name: str, *kinds: Literal["action", "expression"]
    ) -> tuple[MemberForm, ...]:
        """Receiver forms that replace a rejected flat spelling.

        Matches the retired native spellings of each member target (normalized
        native name, record name, interactive label) and the final segment of
        ``name`` (``Character.SetVirtue``), since a card-first target keeps only its
        member form.
        """

        last = name.rsplit(".", 1)[-1]
        found: list[MemberForm] = []
        for kind in kinds:
            found.extend(self._retired_members.get((kind, name.casefold()), ()))
            found.extend(self.policy.member_form_candidates(last, kind=kind))
        return tuple(dict.fromkeys(found))

    def retired_member_names(
        self, name: str, kind: Literal["action", "expression"]
    ) -> tuple[str, ...]:
        """Member names that replace a native fallback spelling used as a member name."""

        forms = self._retired_members.get((kind, name.casefold()), ())
        return tuple(dict.fromkeys(form.name for form in forms))

    def member_form(
        self, kind: NativeKind, identifier: int, scope: TypeId | None = None
    ) -> MemberForm | None:
        """The receiver form that is this target's canonical spelling, or ``None``."""

        return self.policy.member_form_for_target(WireIdentity(kind, identifier, scope))

    def action_candidates(self, name: str) -> tuple[ActionMetadata, ...]:
        if self.root_case_variant(name) is not None:
            return ()
        return tuple(
            cast(ActionMetadata, target.metadata) for target in self.candidates("action", name)
        )

    def event_candidates(self, name: str) -> tuple[EventMetadata, ...]:
        if self.root_case_variant(name) is not None:
            return ()
        return tuple(
            cast(EventMetadata, target.metadata) for target in self.candidates("event", name)
        )

    def expression_candidates(self, name: str) -> tuple[ExpressionMetadata, ...]:
        if self.root_case_variant(name) is not None:
            return ()
        return tuple(
            cast(ExpressionMetadata, target.metadata)
            for target in self.candidates("expression", name)
        )

    def named_constant_candidates(
        self, name: str, value_type: TypeId | None = None
    ) -> tuple[NamedConstantMetadata, ...]:
        if self.root_case_variant(name) is not None:
            return ()
        return tuple(
            cast(NamedConstantMetadata, target.metadata)
            for target in self.candidates("named_constant", name, result_type=value_type)
        )

    def member_forms(
        self,
        member: str,
        *,
        kind: Literal["action", "expression"] | None = None,
        arguments: int | None = None,
    ) -> tuple[MemberForm, ...]:
        """Configured receiver forms by member spelling; the binder selects among them."""

        return self.policy.member_form_candidates(member, kind=kind, arguments=arguments)

    def member_target(self, form: MemberForm) -> ActionMetadata | ExpressionMetadata:
        """Return the native callable a validated member form projects."""

        if form.target.kind == "action":
            action = self.metadata.action(form.target.identifier)
            assert action is not None
            return action
        assert form.target.scope is not None
        expression = self.metadata.expression(form.target.scope, form.target.identifier)
        assert expression is not None
        return expression

    def root_case_variant(self, name: str) -> str | None:
        """Return the registered root that ``name``'s root matches only ignoring case.

        Roots match exactly; segments after the root and unqualified names stay
        case-insensitive. ``None`` means the root is exact, unregistered, or absent.
        """

        if "." not in name:
            return None
        root = name.split(".", 1)[0]
        if root in self.namespace_roots:
            return None
        return self._folded_roots.get(root.casefold())

    def case_rewrite(self, name: str, *kinds: NativeKind) -> str | None:
        """The exact spelling ``name`` means when only its namespace root's case is wrong.

        The tail is resolved ignoring case among the accepted forms of ``kinds``
        (and policy source values for expressions and named constants). ``None``
        when the root is exact, the tail is unknown, or it matches several spellings.
        """

        root = self.root_case_variant(name)
        if root is None:
            return None
        folded = name.casefold()
        spellings = {
            form.spelling
            for form in self.source_forms.values()
            if form.kind != "member"
            and form.target.kind in kinds
            and form.spelling.casefold() == folded
        }
        if "expression" in kinds or "named_constant" in kinds:
            spellings.update(
                item.name for item in self.source_values if item.name.casefold() == folded
            )
        return next(iter(spellings)) if len(spellings) == 1 else None

    def forms(
        self, kind: NativeKind, identifier: int, scope: TypeId | None = None
    ) -> tuple[SourceForm, ...]:
        target = self.native_targets.get(WireIdentity(kind, identifier, scope))
        return () if target is None else target.forms

    def canonical_name(
        self, kind: NativeKind, identifier: int, scope: TypeId | None = None
    ) -> str | None:
        member = self.member_form(kind, identifier, scope)
        if member is not None:
            return member.name
        forms = self.forms(kind, identifier, scope)
        return next((form.spelling for form in forms if form.canonical), None)

    def expression_defect(self, scope: TypeId, identifier: int) -> str | None:
        """Why AAUnlimited cannot run this expression, when policy records a native defect."""

        return self.policy.expression_defect(scope, identifier)

    def expression_is_readable(self, scope: TypeId, identifier: int) -> bool:
        """Whether policy opts a native anomaly into output under its preferred name."""

        preferred = self.policy.preferred_expression_name(scope, identifier)
        return (
            preferred is not None
            and self.policy.is_expression_readable(scope, identifier)
            and any(
                form.reversible and form.spelling.casefold() == preferred.casefold()
                for form in self.forms("expression", identifier, scope)
            )
        )

    def candidates(
        self,
        kind: NativeKind,
        spelling: str,
        *,
        result_type: TypeId | None = None,
        parameter_types: tuple[TypeId, ...] | None = None,
    ) -> tuple[NativeTarget, ...]:
        """Expose exact candidates; never rank, cast, or select by iteration order."""

        targets = (
            self.native_targets[key] for key in self._names.get((kind, spelling.casefold()), ())
        )
        return tuple(
            target
            for target in targets
            if (result_type is None or target.signature.result_type == result_type)
            and (parameter_types is None or target.signature.parameter_types == parameter_types)
        )
