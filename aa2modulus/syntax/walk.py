"""Iterate Source AST nodes without recursion."""

from __future__ import annotations

from collections.abc import Iterator

from ..context.limits import record_children
from .limits import AST_NODES


def walk_ast(nodes: object) -> Iterator[object]:
    """Every AST node in ``nodes`` (a node or nested tuples), parents first."""

    stack = [iter((nodes,))]
    while stack:
        try:
            node = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if isinstance(node, tuple):
            stack.append(iter(node))
        elif isinstance(node, AST_NODES):
            yield node
            stack.append(record_children(node))
