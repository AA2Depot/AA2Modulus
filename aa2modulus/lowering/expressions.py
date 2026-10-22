"""Lower bound expressions to SIR expressions."""

from __future__ import annotations

from ..hir.nodes import (
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
    BoundRawVariable,
    BoundUnary,
    BoundVariable,
)
from ..language.types import wire_type
from ..model.records import Expression, NamedConstantRef
from ..model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR


def lower_expression(node: BoundExpression) -> Expression:
    if isinstance(node, BoundLiteral):
        return Expression(
            node.value.type,
            EXPR_CONSTANT,
            constant=node.value,
            source_span=node.source_span,
        )
    if isinstance(node, BoundVariable):
        return Expression(
            wire_type(node.type),
            EXPR_VAR,
            variable_name=node.name,
            source_span=node.source_span,
        )
    if isinstance(node, BoundNamedConstant):
        metadata = node.metadata
        return Expression(
            metadata.value_type,
            EXPR_NAMEDCONSTANT,
            named_constant=NamedConstantRef(
                metadata.value_type,
                metadata.id,
                metadata=metadata,
                source_span=node.source_span,
            ),
            source_span=node.source_span,
        )
    if isinstance(node, BoundCall):
        expression_metadata = node.metadata
        return Expression(
            expression_metadata.return_type,
            expression_metadata.id,
            parameters=tuple(lower_expression(item) for item in node.arguments),
            metadata=expression_metadata,
            source_span=node.source_span,
        )
    if isinstance(node, BoundCardConversion):
        return lower_expression(node.operand)
    if isinstance(node, BoundUnary):
        return Expression(
            node.operator.return_type,
            node.operator.expression_id,
            parameters=(lower_expression(node.operand),),
            source_span=node.source_span,
        )
    if isinstance(node, BoundBinary):
        return Expression(
            node.operator.return_type,
            node.operator.expression_id,
            parameters=(lower_expression(node.left), lower_expression(node.right)),
            source_span=node.source_span,
        )
    if isinstance(node, BoundRawExpression):
        payload = node.payload
        if isinstance(payload, BoundRawConstant):
            return Expression(
                node.return_type,
                node.identifier,
                constant=payload.value,
                source_span=node.source_span,
                raw_reference=True,
            )
        if isinstance(payload, BoundRawVariable):
            return Expression(
                node.return_type,
                node.identifier,
                variable_name=payload.name,
                source_span=node.source_span,
                raw_reference=True,
            )
        if isinstance(payload, BoundRawNamedConstant):
            return Expression(
                node.return_type,
                node.identifier,
                named_constant=NamedConstantRef(
                    payload.value_type,
                    payload.identifier,
                    source_span=node.source_span,
                    raw_reference=True,
                ),
                source_span=node.source_span,
                raw_reference=True,
            )
        if isinstance(payload, BoundRawParameters):
            return Expression(
                node.return_type,
                node.identifier,
                parameters=tuple(lower_expression(item) for item in payload.parameters),
                source_span=node.source_span,
                raw_reference=True,
            )
    raise TypeError(f"unsupported bound expression: {node!r}")
