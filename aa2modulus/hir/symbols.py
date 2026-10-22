"""Immutable links from authored source names to binder-selected targets."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.locations import SourceSpan
from ..language.types import SourceType
from ..language.values import MemberForm, SourceValue
from ..model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ..model.types import TypeId
from ..model.values import Value
from ..syntax.ast import (
    SourceConstant,
    SourceGlobal,
    SourceLocal,
    SourceMacro,
    SourceParameter,
    SourceTriggerTemplate,
)

type SourceDeclaration = (
    SourceGlobal
    | SourceLocal
    | SourceParameter
    | SourceMacro
    | SourceTriggerTemplate
    | SourceConstant
)
type SelectedMetadata = (
    ActionMetadata | EventMetadata | ExpressionMetadata | NamedConstantMetadata | SourceValue
)


@dataclass(frozen=True, slots=True)
class BoundReference:
    """One authored name use and the target selected by source binding.

    A reference may point to an authored declaration, selected registry metadata,
    or a known variable type supplied by an external context. A receiver-call member
    name also retains the configured form that selected its native target. Raw or unresolved
    uses are omitted by the binder when no target can be established.
    """

    name: str
    source_span: SourceSpan | None
    declaration: SourceDeclaration | None = None
    metadata: SelectedMetadata | None = None
    type: SourceType | None = None
    member_form: MemberForm | None = None
    # The substituted literal when the reference names a compile-time constant.
    value: Value | None = None


@dataclass(frozen=True, slots=True)
class ResolvedConstant:
    """A compile-time constant with its resolved typed literal.

    ``value`` is ``None`` only in editor views, when the constant itself failed to
    resolve. ``top_level`` constants (outside any module) are visible in macros and
    trigger templates; module-item constants are visible only in their module.
    """

    declaration: SourceConstant
    type: TypeId
    value: Value | None
    top_level: bool
