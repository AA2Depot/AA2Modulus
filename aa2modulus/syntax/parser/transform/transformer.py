"""The Lark transformer from parse trees to Source AST.

Lark finds rule handlers by method name, so every mixin method name is unique.
"""

from __future__ import annotations

from .attributes import AttributesMixin
from .declarations import DeclarationsMixin
from .definitions import DefinitionsMixin
from .expressions import ExpressionsMixin
from .literals import LiteralsMixin
from .statements import StatementsMixin


class SourceTransformer(
    AttributesMixin,
    DeclarationsMixin,
    DefinitionsMixin,
    StatementsMixin,
    ExpressionsMixin,
    LiteralsMixin,
):
    """Builds a ``SourceModule`` or ``SourceUnit``; ``allows`` collects ``@allow`` attributes."""
