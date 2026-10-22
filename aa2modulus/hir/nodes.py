"""Source-oriented bound HIR for the unified `.aa2m` compiler.

Bound HIR nodes describe resolved source meaning. They deliberately do not
serialize themselves and do not replace the AA2 Serialized IR in ``model.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.diagnostics import Diagnostic
from ..core.locations import SourceSpan
from ..language.operators import OperatorDefinition
from ..language.types import CARD, SourceType
from ..model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ..model.types import TypeId
from ..model.values import Value
from .symbols import BoundReference


@dataclass(frozen=True, slots=True)
class BoundLiteral:
    value: Value
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)

    @property
    def type(self) -> TypeId:
        return self.value.type


@dataclass(frozen=True, slots=True)
class BoundVariable:
    name: str
    type: SourceType
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundNamedConstant:
    metadata: NamedConstantMetadata
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)

    @property
    def type(self) -> TypeId:
        return self.metadata.value_type


@dataclass(frozen=True, slots=True)
class BoundCall:
    metadata: ExpressionMetadata
    arguments: tuple[BoundExpression, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    # A card-role result (policy `[result_roles]`) has the source type `card`.
    card: bool = field(default=False, kw_only=True)

    @property
    def type(self) -> SourceType:
        return CARD if self.card else self.metadata.return_type


@dataclass(frozen=True, slots=True)
class BoundCardConversion:
    """``Card(expr)``: the operand's ``int`` value typed as ``card``; lowers to the operand."""

    operand: BoundExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)

    @property
    def type(self) -> SourceType:
        return CARD


@dataclass(frozen=True, slots=True)
class BoundUnary:
    operator: OperatorDefinition
    operand: BoundExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)

    @property
    def type(self) -> TypeId:
        return self.operator.return_type


@dataclass(frozen=True, slots=True)
class BoundBinary:
    operator: OperatorDefinition
    left: BoundExpression
    right: BoundExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)

    @property
    def type(self) -> TypeId:
        return self.operator.return_type


@dataclass(frozen=True, slots=True)
class BoundRawConstant:
    value: Value


@dataclass(frozen=True, slots=True)
class BoundRawVariable:
    name: str


@dataclass(frozen=True, slots=True)
class BoundRawNamedConstant:
    value_type: TypeId
    identifier: int


@dataclass(frozen=True, slots=True)
class BoundRawParameters:
    parameters: tuple[BoundExpression, ...] = ()


type BoundRawPayload = (
    BoundRawConstant | BoundRawVariable | BoundRawNamedConstant | BoundRawParameters
)


@dataclass(frozen=True, slots=True)
class BoundRawExpression:
    return_type: TypeId
    identifier: int
    payload: BoundRawPayload
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)

    @property
    def type(self) -> TypeId:
        return self.return_type


type BoundExpression = (
    BoundLiteral
    | BoundVariable
    | BoundNamedConstant
    | BoundCall
    | BoundUnary
    | BoundBinary
    | BoundCardConversion
    | BoundRawExpression
)


@dataclass(frozen=True, slots=True)
class BoundEvent:
    metadata: EventMetadata
    arguments: tuple[BoundExpression, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundRawEvent:
    identifier: int
    arguments: tuple[BoundExpression, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundAction:
    metadata: ActionMetadata
    arguments: tuple[BoundExpression, ...] = ()
    children: tuple[BoundStatement, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundRawAction:
    identifier: int
    arguments: tuple[BoundExpression, ...] = ()
    children: tuple[BoundStatement, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundAssignment:
    variable: BoundVariable
    value: BoundExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundElseIf:
    condition: BoundExpression
    body: tuple[BoundStatement, ...]
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundElse:
    body: tuple[BoundStatement, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundIf:
    condition: BoundExpression
    body: tuple[BoundStatement, ...]
    else_if: tuple[BoundElseIf, ...] = ()
    else_branch: BoundElse | None = None
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundLoop:
    body: tuple[BoundStatement, ...]
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundFor:
    variable: BoundVariable
    start: BoundExpression
    limit: BoundExpression
    body: tuple[BoundStatement, ...]
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundLoopControl:
    keyword: str
    condition: BoundExpression | None = None
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


type BoundStatement = (
    BoundAction
    | BoundRawAction
    | BoundAssignment
    | BoundElseIf
    | BoundElse
    | BoundIf
    | BoundLoop
    | BoundFor
    | BoundLoopControl
)


@dataclass(frozen=True, slots=True)
class BoundLocal:
    name: str
    type: SourceType
    default: BoundExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundGlobal:
    name: str
    type: SourceType
    default: BoundLiteral
    current: BoundLiteral
    initialized: bool
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundTrigger:
    name: str
    events: tuple[BoundEvent | BoundRawEvent, ...] = ()
    locals: tuple[BoundLocal, ...] = ()
    statements: tuple[BoundStatement, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class BoundModule:
    name: str
    description: str = ""
    dependencies: tuple[str, ...] = ()
    globals: tuple[BoundGlobal, ...] = ()
    triggers: tuple[BoundTrigger, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    diagnostics: tuple[Diagnostic, ...] = field(default=(), compare=False, repr=False, kw_only=True)
    references: tuple[BoundReference, ...] = field(
        default=(), compare=False, repr=False, kw_only=True
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "references", tuple(self.references))
