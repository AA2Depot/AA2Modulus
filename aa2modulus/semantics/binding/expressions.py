"""Expressions: names, calls, member calls, operators and raw forms (one recursive group)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ...core.diagnostics import Diagnostic
from ...core.locations import SourceSpan
from ...core.source_names import is_qualified_source_name
from ...hir.nodes import (
    BoundBinary,
    BoundCall,
    BoundCardConversion,
    BoundExpression,
    BoundLiteral,
    BoundNamedConstant,
    BoundRawConstant,
    BoundRawExpression,
    BoundRawNamedConstant,
    BoundRawParameters,
    BoundRawPayload,
    BoundRawVariable,
    BoundUnary,
    BoundVariable,
)
from ...hir.symbols import BoundReference
from ...language.operators import OperatorDefinition
from ...language.types import (
    CARD,
    SourceType,
    member_parameter_types,
    parameter_types,
    result_type,
    wire_type,
)
from ...language.values import MemberForm
from ...model.display import type_name
from ...model.native import ExpressionMetadata
from ...model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, TypeId, ValueType
from ...syntax.ast import (
    SourceBinary,
    SourceCall,
    SourceCardConversion,
    SourceConstantReference,
    SourceExpression,
    SourceGroup,
    SourceLiteral,
    SourceMemberCall,
    SourceMemberProperty,
    SourceName,
    SourceRawConstant,
    SourceRawExpression,
    SourceRawNamedConstant,
    SourceRawParameters,
    SourceRawVariable,
    SourceUnary,
    SourceVariableReference,
    raw_payload_text,
)
from .constants import bind_constant, bind_constant_reference, constant_entry
from .declarations import is_protected
from .members import bind_member_form, dotted_receiver
from .reporting import (
    join_help,
    node_span,
    raise_error,
    record_member_reference,
    record_reference,
    record_variable_reference,
)
from .rewrites import member_fixes, root_fixes
from .state import BindContext, SourceBindingError
from .suggestions import hidden_help, hidden_hint, retired_hint, root_hint
from .values import card_mismatch, check_card_comparison, check_type, literal_like, literal_value


def _bind_card(context: BindContext, node: SourceExpression) -> BoundExpression:
    """Bind a value where a card is expected: a card, an int literal or a constant."""

    bound = bind_expression(context, node, ValueType.INT)
    if bound.type is not CARD and not literal_like(node, bound):
        card_mismatch(context, node)
    return bound


def builtin_call(
    context: BindContext,
    metadata: ExpressionMetadata,
    arguments: tuple[BoundExpression, ...] = (),
    *,
    source_span: SourceSpan | None,
) -> BoundCall:
    """A built-in call, typed ``card`` when policy gives its result the card role."""

    return BoundCall(
        metadata,
        arguments,
        source_span=source_span,
        card=result_type(context.source_policy, metadata) is CARD,
    )


def try_candidates[C, R](
    context: BindContext,
    node: object,
    candidates: Iterable[C],
    attempt: Callable[[C, BindContext, list[BoundExpression]], R],
    *,
    skip: type[Exception] | tuple[type[Exception], ...] = (),
) -> tuple[list[tuple[C, R, list[BoundReference]]], SourceBindingError | None]:
    """Try every candidate in its own reference scope, charging the budget for each.

    ``attempt`` appends each operand it binds to the list it is given. It returns
    the candidate's result, kept with the references recorded while binding it.
    The failure of the candidate that bound the most operands is returned, the
    first one on ties; ``skip`` exceptions rule a candidate out without a failure.
    """

    successes: list[tuple[C, R, list[BoundReference]]] = []
    best_failure: SourceBindingError | None = None
    matched_arguments = -1
    for candidate in candidates:
        context.binding_budget.charge(node_span(node))
        candidate_context = context.fork_references()
        bound: list[BoundExpression] = []
        try:
            result = attempt(candidate, candidate_context, bound)
        except SourceBindingError as exc:
            if len(bound) > matched_arguments:
                best_failure = exc
                matched_arguments = len(bound)
        except skip:
            pass
        else:
            successes.append((candidate, result, candidate_context.references))
    return successes, best_failure


def bind_arguments(
    context: BindContext, pairs: Iterable[tuple[SourceExpression, SourceType | None]]
) -> tuple[BoundExpression, ...]:
    """Bind each argument of a call with one candidate, reporting every failing one.

    Arguments are independent, so one failure does not hide the next; the call
    then fails with all their errors in source order (no partial value escapes).
    """

    bound: list[BoundExpression] = []
    errors: list[Diagnostic] = []
    for argument, expected in pairs:
        try:
            bound.append(bind_expression(context, argument, expected))
        except SourceBindingError as exc:
            errors.extend(exc.diagnostics)
    if errors:
        raise SourceBindingError(errors[0], tuple(errors))
    return tuple(bound)


def bind_expression(
    context: BindContext,
    node: SourceExpression,
    expected: SourceType | None = None,
) -> BoundExpression:
    if expected is CARD:
        return _bind_card(context, node)
    context.binding_budget.charge(node_span(node))
    if isinstance(node, SourceLiteral):
        value = literal_value(context, node)
        check_type(context, value.type, expected, node)
        return BoundLiteral(value, source_span=node_span(node))

    if isinstance(node, SourceGroup):
        return bind_expression(context, node.expression, expected)

    if isinstance(node, SourceCardConversion):
        check_type(context, CARD, expected, node)
        return BoundCardConversion(
            bind_expression(context, node.operand, ValueType.INT), source_span=node_span(node)
        )

    if isinstance(node, SourceVariableReference):
        return _bind_variable_reference(context, node, expected)

    if isinstance(node, SourceConstantReference):
        return bind_constant_reference(context, node.name, node, expected)

    if isinstance(node, SourceName):
        return _bind_name(context, node, expected)

    if isinstance(node, SourceCall):
        return _bind_call(context, node, expected)

    if isinstance(node, SourceMemberCall):
        return _bind_member_call(
            context, node, node.receiver, node.member, node.name_span, node.arguments, expected
        )

    if isinstance(node, SourceMemberProperty):
        return _bind_member_call(
            context, node, node.receiver, node.member, node.name_span, None, expected
        )

    if isinstance(node, SourceUnary):
        return _bind_unary(context, node, expected)

    if isinstance(node, SourceBinary):
        return _bind_binary(context, node, expected)

    if isinstance(node, SourceRawExpression):
        return _bind_raw_expression(context, node, expected)

    raise_error(context, node, "UNSUPPORTED_EXPRESSION", f"unsupported source expression {node!r}")


def _bind_variable_reference(
    context: BindContext, node: SourceVariableReference, expected: SourceType | None
) -> BoundExpression:
    """``variable("...")``: a declared variable; definitions cannot capture outer ones."""

    if context.template_definition is not None and node.name not in context.locals:
        raise_error(
            context, node, "TEMPLATE_CAPTURE", f"template cannot capture variable {node.name!r}"
        )
    if context.macro_definition is not None and node.name not in context.locals:
        raise_error(context, node, "MACRO_CAPTURE", f"macro cannot capture variable {node.name!r}")
    value_type = context.variable_type(node.name)
    if value_type is None:
        help, fixes = context.undeclared_help(node.name, expected)
        raise_error(
            context,
            node,
            "UNDEFINED_VARIABLE",
            f"undefined variable {node.name!r}",
            help=help,
            fixes=fixes,
        )
    check_type(context, value_type, expected, node)
    record_variable_reference(context, node.name, node, value_type)
    return BoundVariable(name=node.name, type=value_type, source_span=node_span(node))


def _bind_unary(
    context: BindContext, node: SourceUnary, expected: TypeId | None
) -> BoundExpression:
    """A prefix operator, selected by its operand type and the expected result."""

    operand = bind_expression(context, node.operand)
    operators = context.source_policy.operator_candidates(
        node.operator, (wire_type(operand.type),), return_type=expected
    )
    if len(operators) != 1:
        raise_error(
            context,
            node,
            "UNKNOWN_OPERATOR_OVERLOAD",
            f"no unique overload for {node.operator!r}",
        )
    return BoundUnary(operator=operators[0], operand=operand, source_span=node_span(node))


def _bind_binary(
    context: BindContext, node: SourceBinary, expected: TypeId | None
) -> BoundExpression:
    """An infix operator: every overload is tried; exactly one must bind."""

    operators = context.source_policy.operator_candidates(node.operator, return_type=expected)

    def attempt(
        operator: OperatorDefinition, candidate_context: BindContext, bound: list[BoundExpression]
    ) -> tuple[BoundExpression, BoundExpression]:
        bound.append(bind_expression(candidate_context, node.left, operator.parameter_types[0]))
        right = bind_expression(candidate_context, node.right, operator.parameter_types[1])
        return bound[0], right

    # An operator with too few parameters cannot match; it is no better failure.
    successes, best_failure = try_candidates(context, node, operators, attempt, skip=IndexError)
    if len(successes) == 1:
        operator, (left, right), references = successes[0]
        if node.operator in {"==", "!="}:
            check_card_comparison(context, node, left, right)
        context.references.extend(references)
        return BoundBinary(operator=operator, left=left, right=right, source_span=node_span(node))
    if len(successes) > 1:
        raise_error(
            context,
            node,
            "UNKNOWN_OPERATOR_OVERLOAD",
            f"ambiguous overload for {node.operator!r}",
        )
    if best_failure is not None:
        raise best_failure
    raise_error(
        context,
        node,
        "UNKNOWN_OPERATOR_OVERLOAD",
        f"no unique overload for {node.operator!r}",
    )


def _bind_name(
    context: BindContext,
    node: SourceName,
    expected: TypeId | None,
) -> BoundExpression:
    """A bare name, tried in order: authored constant, variable, literal source value,
    zero-argument built-in, named constant, then a dotted member receiver.

    Qualified and protected names skip the authored constant and variable lookups.
    """

    qualified = is_qualified_source_name(node.name)
    protected = not qualified and is_protected(context, node.name)
    if not qualified and not protected:
        entry = constant_entry(context, node.name, node)
        if entry is not None:
            return bind_constant(context, entry, node, expected)
    value_type = None if qualified or protected else context.variable_type(node.name)
    if value_type is not None:
        check_type(context, value_type, expected, node)
        record_variable_reference(context, node.name, node, value_type)
        return BoundVariable(name=node.name, type=value_type, source_span=node_span(node))

    source_value = context.catalog.source_value(node.name)
    if source_value is not None:
        check_type(context, source_value.value_type, expected, node)
        record_reference(
            context,
            node.name,
            node,
            metadata=source_value,
            value_type=source_value.value_type,
        )
        return BoundLiteral(source_value.value, source_span=node_span(node))
    zero_argument_candidates = tuple(
        entry
        for entry in context.catalog.expression_candidates(node.name)
        if not entry.parameter_types
    )
    candidates = tuple(
        entry
        for entry in zero_argument_candidates
        if expected is None or entry.return_type == expected
    )
    if len(candidates) == 1:
        record_reference(
            context,
            node.name,
            node,
            metadata=candidates[0],
            value_type=result_type(context.source_policy, candidates[0]),
        )
        return builtin_call(context, candidates[0], source_span=node_span(node))
    if len(candidates) > 1:
        raise_error(
            context, node, "AMBIGUOUS_EXPRESSION_NAME", f"ambiguous expression {node.name!r}"
        )

    constants = context.catalog.named_constant_candidates(node.name, expected)
    if len(constants) == 1:
        record_reference(
            context,
            node.name,
            node,
            metadata=constants[0],
            value_type=constants[0].value_type,
        )
        return BoundNamedConstant(metadata=constants[0], source_span=node_span(node))
    if len(constants) > 1:
        raise_error(
            context, node, "AMBIGUOUS_NAMED_CONSTANT", f"ambiguous named constant {node.name!r}"
        )
    dotted = dotted_receiver(context, node.name, node.name_span)
    if dotted is not None:
        receiver, member, member_span = dotted
        return _bind_member_call(context, node, receiver, member, member_span, None, expected)
    rejected = context.catalog.rejected_constant_name(node.name, expected)
    if rejected is not None:
        raise_error(context, node, "REJECTED_CONSTANT_NAME", rejected[0], help=rejected[1])
    if expected is not None and (
        zero_argument_candidates or context.catalog.named_constant_candidates(node.name, None)
    ):
        raise_error(
            context,
            node,
            "SOURCE_TYPE_MISMATCH",
            f"source name {node.name!r} has no candidate of type {type_name(expected)}",
        )
    raise_error(
        context,
        node,
        "UNKNOWN_EXPRESSION_NAME",
        f"unknown source name {node.name!r}{hidden_hint(context, node.name)}",
        help=join_help(
            root_hint(context, node.name, "expression", "named_constant"),
            hidden_help(context, node.name),
            retired_hint(context, node.name, "expression", "named_constant"),
        ),
        fixes=root_fixes(context, node.name, node.name_span, "expression", "named_constant"),
    )


def _bind_raw_expression(
    context: BindContext,
    node: SourceRawExpression,
    expected: TypeId | None,
) -> BoundRawExpression:
    payload = node.payload
    expected_payload = {
        EXPR_CONSTANT: SourceRawConstant,
        EXPR_VAR: SourceRawVariable,
        EXPR_NAMEDCONSTANT: SourceRawNamedConstant,
    }.get(node.identifier, SourceRawParameters)
    if not isinstance(payload, expected_payload):
        raise_error(
            context,
            node,
            "PAYLOAD_MISMATCH",
            f"raw expression id {node.identifier} requires {raw_payload_text(expected_payload)}",
        )
    bound_payload: BoundRawPayload
    if isinstance(payload, SourceRawConstant):
        bound_payload = BoundRawConstant(literal_value(context, payload.value))
    elif isinstance(payload, SourceRawVariable):
        if context.macro_definition is not None:
            raise_error(
                context,
                node,
                "MACRO_CAPTURE",
                "raw variable references are forbidden in macro definitions",
            )
        if context.template_definition is not None:
            if context.is_slot(payload.name):
                raise_error(
                    context,
                    node,
                    "TEMPLATE_SLOT_RAW_REFERENCE",
                    "raw variable payloads cannot reference value slots",
                )
            if payload.name not in context.locals:
                raise_error(
                    context,
                    node,
                    "TEMPLATE_CAPTURE",
                    f"template cannot capture raw variable {payload.name!r}",
                )
            check_type(context, node.return_type, wire_type(context.locals[payload.name]), node)
        variable_type = context.variable_type(payload.name)
        if variable_type is not None and wire_type(variable_type) == node.return_type:
            record_variable_reference(context, payload.name, payload, variable_type)
        bound_payload = BoundRawVariable(payload.name)
    elif isinstance(payload, SourceRawNamedConstant):
        bound_payload = BoundRawNamedConstant(payload.value_type, payload.identifier)
    else:
        bound_payload = BoundRawParameters(
            bind_arguments(context, ((item, None) for item in payload.parameters))
        )
    result = BoundRawExpression(
        return_type=node.return_type,
        identifier=node.identifier,
        payload=bound_payload,
        source_span=node_span(node),
    )
    check_type(context, node.return_type, expected, node)
    return result


def _bind_call(
    context: BindContext,
    node: SourceCall,
    expected: TypeId | None,
) -> BoundCall:
    named_candidates = context.catalog.expression_candidates(node.name)
    if not named_candidates:
        dotted = dotted_receiver(context, node.name, node.name_span)
        if dotted is not None:
            receiver, member, member_span = dotted
            return _bind_member_call(
                context, node, receiver, member, member_span, node.arguments, expected
            )
        raise_error(
            context,
            node,
            "UNKNOWN_EXPRESSION_NAME",
            f"unknown source expression {node.name!r}",
            help=join_help(
                root_hint(context, node.name, "expression"),
                retired_hint(context, node.name, "expression", arguments=node.arguments),
            ),
            fixes=root_fixes(context, node.name, node.name_span, "expression")
            + member_fixes(context, node, "expression"),
        )
    arity_candidates = tuple(
        entry for entry in named_candidates if len(entry.parameter_types) == len(node.arguments)
    )
    if not arity_candidates:
        raise_error(
            context,
            node,
            "EXPRESSION_ARITY",
            f"expression {node.name!r} has the wrong argument count",
        )
    candidates = tuple(
        entry for entry in arity_candidates if expected is None or entry.return_type == expected
    )
    if not candidates:
        raise_error(
            context,
            node,
            "SOURCE_TYPE_MISMATCH",
            f"expression {node.name!r} has no overload returning "
            f"{'a value' if expected is None else type_name(expected)}",
        )

    def attempt(
        entry: ExpressionMetadata, candidate_context: BindContext, bound: list[BoundExpression]
    ) -> BoundCall:
        pairs = zip(node.arguments, parameter_types(context.source_policy, entry), strict=False)
        if len(candidates) == 1:
            bound.extend(bind_arguments(candidate_context, pairs))
        else:
            for argument, parameter_type in pairs:
                bound.append(bind_expression(candidate_context, argument, parameter_type))
        return builtin_call(context, entry, tuple(bound), source_span=node_span(node))

    successes, best_failure = try_candidates(context, node, candidates, attempt)
    if len(successes) == 1:
        _, call, references = successes[0]
        context.references.extend(references)
        record_reference(context, node.name, node, metadata=call.metadata, value_type=call.type)
        return call
    if len(successes) > 1:
        raise_error(
            context, node, "AMBIGUOUS_EXPRESSION_CALL", f"ambiguous expression call {node.name!r}"
        )
    assert best_failure is not None
    raise best_failure


def bind_member_arguments(
    context: BindContext,
    form: MemberForm,
    receiver: SourceExpression,
    arguments: tuple[SourceExpression, ...],
) -> tuple[BoundExpression, ...]:
    """Bind the receiver once as native slot 0, then the explicit arguments in order."""

    receiver_type, *argument_types = member_parameter_types(form)
    return bind_arguments(
        context,
        (
            (receiver, receiver_type),
            *zip(arguments, argument_types, strict=False),
        ),
    )


def _bind_member_call(
    context: BindContext,
    node: object,
    receiver: SourceExpression,
    member: str,
    member_span: SourceSpan | None,
    arguments: tuple[SourceExpression, ...] | None,
    expected: TypeId | None,
) -> BoundCall:
    """Bind ``receiver.Member(arguments)``, or the property ``receiver.Member`` for ``None``."""

    form = bind_member_form(
        context,
        node,
        receiver,
        member,
        None if arguments is None else len(arguments),
        action=False,
        expected=expected,
    )
    target = context.catalog.member_target(form)
    assert isinstance(target, ExpressionMetadata)
    bound = bind_member_arguments(context, form, receiver, arguments or ())
    record_member_reference(context, member, member_span, target, form)
    return builtin_call(context, target, bound, source_span=node_span(node))
