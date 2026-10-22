"""Authored source choices resolved against registry facts; no compiler state."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.source_names import is_qualified_source_name, is_source_name
from ..metadata.identities import RowIdentity, WireIdentity
from ..model.types import TypeId, ValueType
from ..model.values import Value


def _native_types(types: tuple[TypeId, ...], result: TypeId | None, label: str) -> None:
    if any(
        isinstance(scope, bool) or not isinstance(scope, int) or scope not in range(5)
        for scope in types
    ):
        raise ValueError(f"{label} parameters require supported native types")
    if result is not None and (
        isinstance(result, bool) or not isinstance(result, int) or result not in range(5)
    ):
        raise ValueError(f"{label} results require a supported native type or null")


@dataclass(frozen=True, slots=True)
class SourceValue:
    """A qualified source name lowering to the verified value of a shadowed row."""

    name: str
    row: RowIdentity
    value: Value

    def __post_init__(self) -> None:
        if not is_qualified_source_name(self.name) or not is_source_name(self.name):
            raise ValueError("source value names must be qualified non-keyword source names")

    @property
    def value_type(self) -> TypeId:
        return self.value.type

    @property
    def documentation_key(self) -> str:
        assert self.row.scope is not None
        return f"named-constant-{ValueType(self.row.scope).name.lower()}-{self.row.ordinal}"


@dataclass(frozen=True, slots=True)
class MemberArgument:
    """One explicit member-call argument and the native slot it fills."""

    parameter: int
    name: str
    role: str

    def __post_init__(self) -> None:
        if self.parameter < 1:
            raise ValueError("member arguments cannot use the receiver slot")
        if not is_source_name(self.name, allow_qualified=False):
            raise ValueError("member argument names require unqualified non-keyword names")
        if not isinstance(self.role, str) or not self.role.strip():
            raise ValueError("member argument roles require nonempty text")


@dataclass(frozen=True, slots=True)
class MemberForm:
    """A ``receiver.Member(arguments)`` projection of one native callable.

    The receiver fills native slot 0 and the explicit arguments fill the
    remaining slots in order, so lowering reorders, drops and copies nothing.
    Role ``card`` types the receiver or an argument as a source ``card`` (still
    a native ``int``); other roles document. The signature is copied from the
    native target when the policy is read.
    """

    name: str
    target: WireIdentity
    parameter_types: tuple[TypeId, ...]
    result_type: TypeId | None
    receiver_parameter: int
    receiver_role: str
    arguments: tuple[MemberArgument, ...]

    def __post_init__(self) -> None:
        if not is_source_name(self.name, allow_qualified=False):
            raise ValueError("member form names require unqualified non-keyword names")
        if self.target.kind not in ("action", "expression"):
            raise ValueError("member forms target a native action or expression")
        _native_types(self.parameter_types, self.result_type, "member form")
        if isinstance(self.receiver_parameter, bool) or self.receiver_parameter != 0:
            raise ValueError("member forms initially support only native slot 0 receivers")
        if not isinstance(self.receiver_role, str) or not self.receiver_role.strip():
            raise ValueError("member form receivers require a nonempty role")
        if tuple(item.parameter for item in self.arguments) != tuple(
            range(1, len(self.arguments) + 1)
        ) or len(self.arguments) + 1 != len(self.parameter_types):
            raise ValueError(
                "member form arguments must fill native slots 1..n exactly once, in order"
            )
        names = [item.name.casefold() for item in self.arguments]
        if len(set(names)) != len(names):
            raise ValueError("member form argument names must be distinct")

    @property
    def key(self) -> str:
        scope = "" if self.target.scope is None else str(int(self.target.scope))
        return f"member:{self.target.kind}:{scope}:{self.target.identifier}:{self.name.casefold()}"

    @property
    def argument_types(self) -> tuple[TypeId, ...]:
        return self.parameter_types[1:]

    @property
    def receiver_type(self) -> TypeId:
        return self.parameter_types[0]


@dataclass(frozen=True, slots=True)
class EventValues:
    """An expression whose native callback reads event data, so its type depends on the event.

    ``events`` lists, per value type, the events in which the callback returns
    event data of that type; in every other event it returns ``otherwise``.
    """

    target: WireIdentity
    callback: str
    events: tuple[tuple[TypeId, tuple[int, ...]], ...]
    otherwise: Value

    def value_type(self, event_id: int) -> TypeId:
        """The type the callback returns during ``event_id``."""

        for value_type, event_ids in self.events:
            if event_id in event_ids:
                return value_type
        return self.otherwise.type

    def literal(self, event_id: int) -> Value | None:
        """The fixed value returned during ``event_id``, or None when it reads event data."""

        if any(event_id in event_ids for _, event_ids in self.events):
            return None
        return self.otherwise

    def field_events(self, value_type: TypeId) -> tuple[int, ...]:
        """Events in which the callback returns event data of ``value_type``."""

        return next((ids for scope, ids in self.events if scope == value_type), ())


@dataclass(frozen=True, slots=True)
class ActionDefault:
    """A source-level trailing argument default for one serialized action."""

    action_id: int
    parameter_index: int
    value: Value

    def __post_init__(self) -> None:
        if self.action_id < 1:
            raise ValueError("action IDs must be positive")
        if self.parameter_index < 0:
            raise ValueError("parameter indexes cannot be negative")
