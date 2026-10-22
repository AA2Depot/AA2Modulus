"""Expression rendering: literals, names, operators, member chains and raw fallbacks."""

from __future__ import annotations

from typing import Literal

from ...core.source_names import is_qualified_source_name, is_source_name
from ...language.operators import OperatorDefinition
from ...language.types import CARD, SourceType, member_parameter_types, parameter_types
from ...language.values import MemberForm
from ...model.native import ExpressionMetadata
from ...model.records import Expression, NamedConstantRef
from ...model.types import (
    EXPR_CONSTANT,
    EXPR_NAMEDCONSTANT,
    EXPR_PAYLOAD_MARKERS,
    EXPR_VAR,
    TypeId,
    ValueType,
)
from .cards import card_comparison, card_text, is_card_text, is_int_literal
from .context import (
    FormatContext,
    catalog_name,
    is_bare_variable_name,
    operator_text,
)
from .fallbacks import (
    expression_fallback_reason,
)
from .text import FormatError, literal, quote, raw_value, type_name


def positioned_text(
    expression: Expression,
    context: FormatContext,
    expected: SourceType | None,
    wire: TypeId | None,
) -> str:
    """Render an argument whose source type is ``expected`` (``CARD`` or a wire type)."""

    text = expression_text(expression, context, expected_type=wire)
    return card_text(expression, text, context) if expected is CARD else text


def _raw_expression(
    expression: Expression,
    context: FormatContext,
    indent: int = 0,
    *,
    reason: str | None = None,
) -> list[str]:
    if reason is None:
        reason = expression_fallback_reason(expression, context)
    context.raw_fallback(expression, reason)
    pad = " " * indent
    lines = [f"{pad}raw_expression {type_name(expression.return_type)} {expression.id} {{"]
    child = " " * (indent + 2)
    if expression.id == EXPR_CONSTANT and expression.constant is not None:
        lines.append(f"{child}constant {raw_value(expression.constant)};")
    elif expression.id == EXPR_VAR and expression.variable_name is not None:
        lines.append(f"{child}variable {quote(expression.variable_name)};")
    elif expression.id == EXPR_NAMEDCONSTANT and expression.named_constant is not None:
        reference = expression.named_constant
        lines.append(f"{child}named_constant {type_name(reference.value_type)} {reference.id};")
    else:
        lines.append(f"{child}parameters [")
        for parameter in expression.parameters:
            lines.append(f"{child}  {expression_text(parameter, context)}")
        lines.append(f"{child}];")
    lines.append(f"{pad}}}")
    return lines


def _expression_native_metadata(
    expression: Expression,
    context: FormatContext,
) -> ExpressionMetadata | None:
    """Registry metadata when the record matches its declaration."""

    metadata = expression.metadata or context.metadata.expression(
        expression.return_type,
        expression.id,
    )
    if (
        metadata is None
        or metadata.id != expression.id
        or metadata.return_type != expression.return_type
        or (
            metadata.declared_return_type != expression.return_type
            and not context.catalog.expression_is_readable(expression.return_type, expression.id)
        )
        or expression.id in EXPR_PAYLOAD_MARKERS
        or tuple(item.return_type for item in expression.parameters) != metadata.parameter_types
    ):
        return None
    return metadata


def _expression_metadata(
    expression: Expression,
    context: FormatContext,
    expected_type: TypeId | None,
) -> ExpressionMetadata | None:
    metadata = _expression_native_metadata(expression, context)
    if metadata is None:
        return None
    name = catalog_name(context, "expression", expression.id, expression.return_type)
    if name is None or not is_source_name(name):
        return None
    candidates = context.catalog.expression_candidates(name)
    actual_parameters = tuple(item.return_type for item in expression.parameters)
    matching = tuple(
        item
        for item in candidates
        if item.parameter_types == actual_parameters
        and (expected_type is None or item.return_type == expected_type)
    )
    if (
        len(matching) != 1
        or matching[0].id != expression.id
        or matching[0].return_type != expression.return_type
    ):
        return None
    return metadata


def expression_text(
    expression: Expression,
    context: FormatContext,
    parent_precedence: int = 0,
    expected_type: TypeId | None = None,
) -> str:
    if expression.raw_reference:
        return _raw_expression_inline(expression, context, "explicit raw provenance")
    if expected_type is not None and expression.return_type != expected_type:
        return _raw_expression_inline(
            expression,
            context,
            expression_fallback_reason(expression, context, expected_type),
        )
    if expression.id == EXPR_CONSTANT and expression.constant is not None:
        if (
            expression.constant.type != expression.return_type
            or expression.constant.type is ValueType.INVALID
        ):
            return _raw_expression_inline(expression, context)
        return literal(expression.constant)
    if expression.id == EXPR_VAR and expression.variable_name is not None:
        if context.variables.get(expression.variable_name) != expression.return_type:
            return _raw_expression_inline(expression, context)
        if is_bare_variable_name(expression.variable_name, context):
            return expression.variable_name
        return f"variable({quote(expression.variable_name)})"
    if expression.id == EXPR_NAMEDCONSTANT and expression.named_constant is not None:
        return _named_constant_text(expression, expression.named_constant, context, expected_type)
    operator_info = operator_text(expression, context)
    if operator_info is not None:
        operator, precedence = operator_info
        return _operator_expression_text(
            expression, operator, precedence, parent_precedence, context
        )
    member = context.catalog.member_form("expression", expression.id, expression.return_type)
    if member is not None:
        return _member_expression_text(expression, member, context, expected_type)
    return _call_text(expression, context, expected_type)


def _named_constant_text(
    expression: Expression,
    reference: NamedConstantRef,
    context: FormatContext,
    expected_type: TypeId | None,
) -> str:
    named_metadata = reference.metadata or context.metadata.named_constant(
        reference.value_type,
        reference.id,
    )
    if (
        reference.raw_reference
        or reference.value_type != expression.return_type
        or named_metadata is None
        or named_metadata.id != reference.id
        or named_metadata.value_type != reference.value_type
    ):
        return _raw_expression_inline(
            expression,
            context,
            expression_fallback_reason(expression, context, expected_type),
        )
    forms = context.catalog.forms("named_constant", reference.id, reference.value_type)
    names = tuple(
        form.spelling
        for form in sorted(forms, key=lambda item: not item.canonical)
        if form.reversible
    )
    for name in names:
        matches = context.catalog.named_constant_candidates(name, reference.value_type)
        expression_matches = context.catalog.expression_candidates(name)
        if (
            len(matches) == 1
            and matches[0].id == reference.id
            and matches[0].value_type == reference.value_type
            and not expression_matches
            and (is_qualified_source_name(name) or name not in context.variables)
        ):
            return name
    return _raw_expression_inline(
        expression,
        context,
        "ambiguous source spelling",
    )


def _operator_expression_text(
    expression: Expression,
    operator: OperatorDefinition,
    precedence: int,
    parent_precedence: int,
    context: FormatContext,
) -> str:
    if operator.fixity == "prefix":
        if len(expression.parameters) == 1:
            operand = expression_text(
                expression.parameters[0],
                context,
                precedence,
            )
            text = f"{operator.token}{operand}"
        else:
            raise FormatError("prefix operator has invalid parameter count")
    elif len(expression.parameters) == 2:
        # Comparison productions permit one operator per tier. Group an
        # equal-precedence child on either side to preserve its tree.
        left_precedence = precedence + (operator.token in {"==", "!=", "<", "<=", ">", ">="})
        left = expression_text(
            expression.parameters[0],
            context,
            left_precedence,
        )
        right_precedence = precedence + (1 if operator.associativity == "left" else 0)
        right = expression_text(
            expression.parameters[1],
            context,
            right_precedence,
        )
        if operator.token in {"==", "!="} and operator.parameter_types == (
            ValueType.INT,
            ValueType.INT,
        ):
            left, right = card_comparison(expression.parameters, left, right, context)
        text = f"{left} {operator.token} {right}"
    else:
        raise FormatError("infix operator has invalid parameter count")
    if precedence < parent_precedence:
        return f"({text})"
    return text


def _call_text(expression: Expression, context: FormatContext, expected_type: TypeId | None) -> str:
    """Write an expression as a call of its canonical name (or the bare name)."""

    metadata = _expression_metadata(expression, context, expected_type)
    if metadata is None:
        return _raw_expression_inline(
            expression,
            context,
            expression_fallback_reason(expression, context, expected_type),
        )
    canonical_name = catalog_name(context, "expression", expression.id, expression.return_type)
    if canonical_name is None:
        return _raw_expression_inline(expression, context)
    if not is_source_name(canonical_name):
        return _raw_expression_inline(expression, context)
    arguments = ", ".join(
        positioned_text(item, context, expected, wire)
        for item, expected, wire in zip(
            expression.parameters,
            parameter_types(context.policy, metadata),
            metadata.parameter_types,
            strict=False,
        )
    )
    if (
        not arguments
        and not expression.parameters
        and (
            is_qualified_source_name(canonical_name)
            or canonical_name.casefold() in context.catalog.protected_names
            or canonical_name not in context.variables
        )
    ):
        return canonical_name
    return f"{canonical_name}({arguments})"


def member_is_unique(
    member: MemberForm, context: FormatContext, expected_type: TypeId | None
) -> bool:
    """Whether the binder resolves ``Name`` with this arity (and type) to exactly ``member``."""

    kind: Literal["action", "expression"] = (
        "action" if member.target.kind == "action" else "expression"
    )
    candidates = context.catalog.member_forms(
        member.name, kind=kind, arguments=len(member.arguments)
    )
    if kind == "expression" and expected_type is not None:
        candidates = tuple(item for item in candidates if item.result_type == expected_type)
    return candidates == (member,)


def receiver_text(receiver: Expression, member: MemberForm, context: FormatContext) -> str | None:
    """Write native slot 0 as a member receiver, or ``None`` when it cannot be one safely."""

    if receiver.raw_reference or receiver.return_type != member.receiver_type:
        return None
    text = expression_text(receiver, context, expected_type=member.receiver_type)
    if text.startswith("raw_expression "):
        return None
    if (
        member_parameter_types(member)[0] is CARD
        and not is_int_literal(receiver)
        and not is_card_text(receiver, text, context)
    ):
        return f"Card({text})"
    if receiver.id == EXPR_VAR:
        if text in context.catalog.namespace_roots:
            # A bare identifier equal to a namespace root would resolve as the root.
            return f"variable({quote(text)})"
        return text
    if (
        receiver.id == EXPR_CONSTANT
        or receiver.id == EXPR_NAMEDCONSTANT
        or operator_text(receiver, context) is not None
    ):
        return f"({text})"
    # Member chains, bare built-ins and built-in calls (`ThisCard()`, `Conversation.Actor(0)`)
    # are valid postfix receivers as written.
    return text


def _member_expression_text(
    expression: Expression,
    member: MemberForm,
    context: FormatContext,
    expected_type: TypeId | None,
) -> str:
    metadata = _expression_native_metadata(expression, context)
    if metadata is None:
        return _raw_expression_inline(
            expression, context, expression_fallback_reason(expression, context, expected_type)
        )
    if (
        member.parameter_types != metadata.parameter_types
        or member.result_type != expression.return_type
    ):
        return _raw_expression_inline(
            expression, context, "declaration mismatch: member form does not match its target"
        )
    if not member_is_unique(member, context, expected_type):
        return _raw_expression_inline(
            expression,
            context,
            f"ambiguous source spelling: member {member.name!r} has no unique overload",
        )
    mark = len(context.diagnostics)
    receiver = receiver_text(expression.parameters[0], member, context)
    if receiver is None:
        del context.diagnostics[mark:]
        return _raw_expression_inline(
            expression, context, f"member {member.name!r} receiver cannot be written as a receiver"
        )
    if not member.arguments:
        return f"{receiver}.{member.name}"
    arguments = ", ".join(
        positioned_text(item, context, expected, wire)
        for item, expected, wire in zip(
            expression.parameters[1:],
            member_parameter_types(member)[1:],
            member.argument_types,
            strict=False,
        )
    )
    return f"{receiver}.{member.name}({arguments})"


def _raw_expression_inline(
    expression: Expression,
    context: FormatContext,
    reason: str | None = None,
) -> str:
    return " ".join(line.strip() for line in _raw_expression(expression, context, reason=reason))
