"""Source-only value types layered over native wire types.

``card`` is a seat that lowers to a native ``int``. It is deliberately not an
``int`` subclass, so code typed for wire ``TypeId`` values cannot receive it
without an explicit :func:`wire_type` conversion.
"""

from __future__ import annotations

from enum import Enum

from ..metadata.identities import WireIdentity
from ..model.display import type_name
from ..model.native import ActionMetadata, ExpressionMetadata
from ..model.types import TypeId, ValueType
from .policy import LanguagePolicy
from .values import MemberForm


class CardType(Enum):
    """The source ``card`` type: a seat value written to the wire as ``int``."""

    CARD = "card"

    def __repr__(self) -> str:
        return "CARD"


CARD = CardType.CARD
type SourceType = TypeId | CardType

CARD_ROLE = "card"
"""The policy role that types a native ``int`` slot or result as ``card``."""


def wire_type(value: SourceType) -> TypeId:
    """The native type a source type lowers to."""

    return ValueType.INT if value is CARD else value


def role_type(wire: TypeId, role: str | None) -> SourceType:
    """The source type of a native slot or result with a policy role."""

    return CARD if role == CARD_ROLE and wire == ValueType.INT else wire


def source_type_name(value: SourceType) -> str:
    """Render a source type as written in source."""

    return "card" if value is CARD else type_name(value)


def widens_to(actual: SourceType, expected: SourceType) -> bool:
    """Whether a value of ``actual`` type is accepted where ``expected`` is required.

    ``card`` widens to ``int``; nothing widens to ``card`` (literal-like values
    are accepted as cards by the binder, which sees the source form).
    """

    return actual == expected or (actual is CARD and expected == ValueType.INT)


def result_type(policy: LanguagePolicy, metadata: ExpressionMetadata) -> SourceType:
    """The source type of an expression's result (``card`` for a card-role result)."""

    return role_type(
        metadata.return_type, policy.expression_result_role(metadata.return_type, metadata.id)
    )


def parameter_types(
    policy: LanguagePolicy, metadata: ActionMetadata | ExpressionMetadata
) -> tuple[SourceType, ...]:
    """The source types of a flat target's native slots (``card`` for card-role slots)."""

    target = (
        WireIdentity("action", metadata.id)
        if isinstance(metadata, ActionMetadata)
        else WireIdentity("expression", metadata.id, metadata.return_type)
    )
    roles = policy.parameter_roles(target)
    if roles is None:
        return tuple(metadata.parameter_types)
    return tuple(
        role_type(kind, role) for kind, role in zip(metadata.parameter_types, roles, strict=False)
    )


def member_parameter_types(form: MemberForm) -> tuple[SourceType, ...]:
    """The source types of a member form's receiver then explicit arguments."""

    return (
        role_type(form.receiver_type, form.receiver_role),
        *(
            role_type(kind, item.role)
            for kind, item in zip(form.argument_types, form.arguments, strict=True)
        ),
    )
