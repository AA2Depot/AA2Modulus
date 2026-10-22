"""Syntax-only AST for the unified `.aa2m` source language.

These nodes retain source intent and locations. Readable forms keep names and
operators until binding; explicit raw forms retain numeric IDs, type scopes,
and payload branches supplied by the author for exact recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.locations import SourceSpan
from ..language.types import SourceType
from ..model.types import TypeId, ValuePayload


@dataclass(frozen=True, slots=True)
class FloatBitsLiteral:
    """A source literal carrying exact IEEE-754 binary32 bits."""

    bits: int
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not 0 <= self.bits <= 0xFFFFFFFF:
            raise ValueError("float bit literals require an unsigned 32-bit value")


type SourceLiteralValue = ValuePayload | FloatBitsLiteral


@dataclass(frozen=True, slots=True)
class SourceLiteral:
    value: SourceLiteralValue
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceName:
    name: str
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceCall:
    name: str
    arguments: tuple[SourceExpression, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceMemberCall:
    """A postfix ``receiver.Member(arguments)`` value call on an explicit receiver."""

    receiver: SourceExpression
    member: str
    arguments: tuple[SourceExpression, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceMemberProperty:
    """A postfix ``receiver.Member`` property read (no parentheses) on an explicit receiver.

    ``name_span`` covers only the member segment; ``source_span`` covers the
    receiver through the member.
    """

    receiver: SourceExpression
    member: str
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceUnary:
    operator: str
    operand: SourceExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceBinary:
    operator: str
    left: SourceExpression
    right: SourceExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceGroup:
    expression: SourceExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceCardConversion:
    """``Card(expr)``: a source-only conversion of an ``int`` to ``card``; no wire record."""

    operand: SourceExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceVariableReference:
    name: str
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceConstantReference:
    """An explicit ``const("Name")`` use; it resolves only compile-time constants."""

    name: str
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceRawExpression:
    return_type: TypeId
    identifier: int
    payload: SourceRawExpressionPayload
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceRawConstant:
    value: SourceLiteral


@dataclass(frozen=True, slots=True)
class SourceRawVariable:
    name: str
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceRawNamedConstant:
    value_type: TypeId
    identifier: int


@dataclass(frozen=True, slots=True)
class SourceRawParameters:
    parameters: tuple[SourceExpression, ...] = ()


type SourceRawExpressionPayload = (
    SourceRawConstant | SourceRawVariable | SourceRawNamedConstant | SourceRawParameters
)
type SourceExpression = (
    SourceLiteral
    | SourceName
    | SourceCall
    | SourceMemberCall
    | SourceMemberProperty
    | SourceUnary
    | SourceBinary
    | SourceGroup
    | SourceCardConversion
    | SourceVariableReference
    | SourceConstantReference
    | SourceRawExpression
)


@dataclass(frozen=True, slots=True)
class SourceEvent:
    name: str | None = None
    identifier: int | None = None
    arguments: tuple[SourceExpression, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)

    def __post_init__(self) -> None:
        if (self.name is None) == (self.identifier is None):
            raise ValueError("source events require exactly one name or numeric ID")


@dataclass(frozen=True, slots=True)
class SourceAction:
    name: str | None = None
    identifier: int | None = None
    arguments: tuple[SourceExpression, ...] = ()
    children: tuple[SourceStatement, ...] = ()
    has_block: bool = field(default=False, kw_only=True)
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    # The `{ ... }` block, for fixes that rewrite the header before it.
    block_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)

    def __post_init__(self) -> None:
        if (self.name is None) == (self.identifier is None):
            raise ValueError("source actions require exactly one name or numeric ID")


@dataclass(frozen=True, slots=True)
class SourceMemberAction:
    """A postfix ``receiver.Member(arguments);`` statement; it never takes a block."""

    receiver: SourceExpression
    member: str
    arguments: tuple[SourceExpression, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    # False for a bare ``receiver.Member;`` statement, which the binder rejects.
    has_parentheses: bool = field(default=True, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceAssignment:
    target: str
    value: SourceExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    target_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    # True for ``variable("Name") = ...``, which never names a constant.
    explicit_variable: bool = field(default=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceParameter:
    name: str
    type: SourceType
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    quoted_name: bool = field(default=False, compare=False, repr=False, kw_only=True)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("source parameter name cannot be empty")


@dataclass(frozen=True, slots=True)
class SourceElseIf:
    condition: SourceExpression
    body: tuple[SourceStatement, ...]
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceElse:
    body: tuple[SourceStatement, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceLocal:
    name: str
    type: SourceType
    default: SourceExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    quoted_name: bool = field(default=False, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceConstant:
    """A compile-time ``const`` declaration; it never reaches HIR names, SIR or the binary.

    ``value`` is a literal, a bare constant name (``SourceName``) or ``const("X")``.
    """

    name: str
    type: TypeId
    value: SourceLiteral | SourceName | SourceConstantReference
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    quoted_name: bool = field(default=False, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceGlobal:
    name: str
    type: SourceType
    default: SourceLiteral | SourceName | SourceConstantReference | None = None
    current: SourceLiteral | None = None
    initialized: bool | None = None
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    quoted_name: bool = field(default=False, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceIf:
    condition: SourceExpression
    body: tuple[SourceStatement, ...]
    else_if: tuple[SourceElseIf, ...] = ()
    else_branch: SourceElse | None = None
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceLoop:
    body: tuple[SourceStatement, ...]
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SourceFor:
    target: str
    start: SourceExpression
    limit: SourceExpression
    body: tuple[SourceStatement, ...]
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    target_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    quoted_name: bool = field(default=False, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceLoopControl:
    keyword: str
    condition: SourceExpression | None = None
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)


type SourceStatement = (
    SourceAction
    | SourceMemberAction
    | SourceAssignment
    | SourceElseIf
    | SourceElse
    | SourceIf
    | SourceLoop
    | SourceFor
    | SourceLoopControl
)


@dataclass(frozen=True, slots=True)
class SourceMacro:
    name: str
    parameters: tuple[SourceParameter, ...]
    body: tuple[SourceStatement, ...]
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("source macro name cannot be empty")
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "body", tuple(self.body))


@dataclass(frozen=True, slots=True)
class SourceImport:
    path: str
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    path_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceSlotBinding:
    name: str
    value: SourceExpression
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceTrigger:
    name: str
    events: tuple[SourceEvent, ...] = ()
    locals: tuple[SourceLocal, ...] = ()
    statements: tuple[SourceStatement, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class SourceTriggerImport:
    template: str
    name: str | None = None
    slots: tuple[SourceSlotBinding, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    template_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", tuple(self.slots))


@dataclass(frozen=True, slots=True)
class SourceTriggerTemplate:
    trigger: SourceTrigger
    slots: tuple[SourceParameter, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", tuple(self.slots))

    @property
    def name(self) -> str:
        return self.trigger.name


@dataclass(frozen=True, slots=True)
class SourceModule:
    name: str
    description: str = ""
    dependencies: tuple[str, ...] = ()
    globals: tuple[SourceGlobal, ...] = ()
    triggers: tuple[SourceTrigger | SourceTriggerImport, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    name_span: SourceSpan | None = field(default=None, compare=False, repr=False, kw_only=True)
    # Module-item constants, visible only inside this module.
    constants: tuple[SourceConstant, ...] = field(default=(), kw_only=True)


STATEMENT_TYPES = (
    SourceAction,
    SourceMemberAction,
    SourceAssignment,
    SourceElseIf,
    SourceElse,
    SourceIf,
    SourceLoop,
    SourceFor,
    SourceLoopControl,
)


@dataclass(frozen=True, slots=True)
class SourceAllow:
    """One ``@allow(CODE, ...)`` attribute and the item it covers.

    Source-only: it changes diagnostic severity and never reaches HIR or SIR.
    ``source_span`` is the attribute, ``target_span`` the item after it, and
    ``code_spans`` locate each code in ``codes``.
    """

    codes: tuple[str, ...]
    code_spans: tuple[SourceSpan, ...]
    source_span: SourceSpan
    target_span: SourceSpan

    def __post_init__(self) -> None:
        object.__setattr__(self, "codes", tuple(self.codes))
        object.__setattr__(self, "code_spans", tuple(self.code_spans))
        if not self.codes or len(self.codes) != len(self.code_spans):
            raise ValueError("source allow needs one span per code")


@dataclass(frozen=True, slots=True)
class SourceUnit:
    module: SourceModule | None
    macros: tuple[SourceMacro, ...] = ()
    source_span: SourceSpan | None = field(default=None, compare=False, repr=False)
    imports: tuple[SourceImport, ...] = field(default=(), kw_only=True)
    templates: tuple[SourceTriggerTemplate, ...] = field(default=(), kw_only=True)
    # Top-level constants (after import composition, the transitive namespace).
    constants: tuple[SourceConstant, ...] = field(default=(), kw_only=True)
    # `@allow` attributes in source order (after import composition, every file's).
    allows: tuple[SourceAllow, ...] = field(default=(), kw_only=True)

    def __post_init__(self) -> None:
        object.__setattr__(self, "allows", tuple(self.allows))
        object.__setattr__(self, "macros", tuple(self.macros))
        object.__setattr__(self, "imports", tuple(self.imports))
        object.__setattr__(self, "templates", tuple(self.templates))
        object.__setattr__(self, "constants", tuple(self.constants))


def raw_payload_text(payload: type) -> str:
    """Plain wording for the payload a raw expression ID requires."""

    if payload is SourceRawConstant:
        return "a constant payload"
    if payload is SourceRawVariable:
        return "a variable payload"
    if payload is SourceRawNamedConstant:
        return "a named-constant payload"
    return "a parameters payload"
