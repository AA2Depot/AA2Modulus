"""Budgets checked on source text, the Lark parse tree and the Source AST."""

from __future__ import annotations

from collections.abc import Iterator

from lark import Token, Tree

from ..context.limits import SourceLimits, check_records, limit_error
from ..core.locations import SourceSpan
from . import ast


def check_source_text(source: str, *, filename: str, limits: SourceLimits) -> None:
    if len(source) > limits.max_source_chars:
        limit_error(
            filename,
            None,
            "SOURCE_SIZE_LIMIT",
            f"source exceeds the character limit of {limits.max_source_chars}",
        )


def _tree_span(node: Tree[Token] | Token, filename: str) -> SourceSpan | None:
    position = node.meta if isinstance(node, Tree) else node
    line = getattr(position, "line", None)
    column = getattr(position, "column", None)
    if isinstance(line, int) and isinstance(column, int):
        return SourceSpan(
            filename,
            line,
            column,
            getattr(position, "end_line", None) or line,
            max(1, (getattr(position, "end_column", None) or column + 1) - 1),
        )
    return None


def check_source_tree(tree: Tree[Token], *, filename: str, limits: SourceLimits) -> None:
    """Inspect Lark's tree iteratively before any AST transformation.

    Token leaves count toward the node budget, but only tree levels contribute
    to syntax depth. A wide tree uses one iterator rather than a wide work stack.
    """

    stack: list[tuple[Iterator[Tree[Token] | Token], int]] = [(iter((tree,)), 1)]
    count = 0
    while stack:
        children, depth = stack[-1]
        node = next(children, None)
        if node is None:
            stack.pop()
            continue
        count += 1
        if count > limits.max_nodes:
            limit_error(
                filename,
                _tree_span(node, filename),
                "SOURCE_NODE_LIMIT",
                f"parse tree exceeds the node limit of {limits.max_nodes}",
            )
        if isinstance(node, Tree):
            if depth > limits.max_syntax_depth:
                limit_error(
                    filename,
                    _tree_span(node, filename),
                    "SOURCE_DEPTH_LIMIT",
                    f"parse tree exceeds the syntax depth limit of {limits.max_syntax_depth}",
                )
            stack.append((iter(node.children), depth + 1))


AST_NODES = (
    ast.SourceModule,
    ast.SourceUnit,
    ast.SourceImport,
    ast.SourceMacro,
    ast.SourceParameter,
    ast.SourceTrigger,
    ast.SourceTriggerImport,
    ast.SourceTriggerTemplate,
    ast.SourceSlotBinding,
    ast.SourceGlobal,
    ast.SourceConstant,
    ast.SourceLocal,
    ast.SourceEvent,
    ast.SourceAction,
    ast.SourceMemberAction,
    ast.SourceAssignment,
    ast.SourceElseIf,
    ast.SourceElse,
    ast.SourceIf,
    ast.SourceLoop,
    ast.SourceFor,
    ast.SourceLoopControl,
    ast.SourceLiteral,
    ast.SourceName,
    ast.SourceCall,
    ast.SourceMemberCall,
    ast.SourceMemberProperty,
    ast.SourceUnary,
    ast.SourceBinary,
    ast.SourceGroup,
    ast.SourceCardConversion,
    ast.SourceVariableReference,
    ast.SourceConstantReference,
    ast.SourceRawExpression,
    ast.SourceRawConstant,
    ast.SourceRawVariable,
    ast.SourceRawNamedConstant,
    ast.SourceRawParameters,
    ast.FloatBitsLiteral,
)
AST_NESTED_NODES = (
    ast.SourceAction,
    ast.SourceMemberAction,
    ast.SourceMacro,
    ast.SourceAssignment,
    ast.SourceElseIf,
    ast.SourceElse,
    ast.SourceIf,
    ast.SourceLoop,
    ast.SourceFor,
    ast.SourceLoopControl,
    ast.SourceLiteral,
    ast.SourceName,
    ast.SourceCall,
    ast.SourceMemberCall,
    ast.SourceMemberProperty,
    ast.SourceUnary,
    ast.SourceBinary,
    ast.SourceCardConversion,
    ast.SourceVariableReference,
    ast.SourceConstantReference,
    ast.SourceRawExpression,
)


def check_source_ast(
    module: ast.SourceModule | ast.SourceUnit,
    *,
    filename: str,
    limits: SourceLimits,
) -> None:
    check_records(
        module,
        filename=filename,
        limits=limits,
        phase="syntax tree",
        node_types=AST_NODES,
        nested_types=AST_NESTED_NODES,
    )
