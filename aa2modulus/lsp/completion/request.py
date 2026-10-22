"""Per-request inputs and per-cursor state shared by the completion modules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lark import Token
from lsprotocol import types

from ...context.operation import SourceContext
from ...pipeline.analysis import SourceAnalysis
from ...pipeline.authoring import SourceAuthoring
from ..protocol.positions import PositionCodec, position_codec
from .scope import authoring_view
from .tokens import Prefix


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """What the client asked for: the document, the cursor and the client's capabilities."""

    source: str
    offset: int
    context: SourceContext
    encoding: str = "utf-16"
    analysis: SourceAnalysis | None = None
    authoring: SourceAuthoring | None = None
    texts: Mapping[str, str] | None = None
    snippet_support: bool = False

    @property
    def codec(self) -> PositionCodec:
        return position_codec(self.source, encoding=self.encoding)

    @property
    def source_texts(self) -> Mapping[str, str]:
        """Texts used to read declaration comments; defaults to this document alone."""

        if self.texts is not None:
            return self.texts
        return {self.context.filename: self.source}

    def view(self) -> SourceAuthoring:
        return authoring_view(self.source, self.context, self.analysis, self.authoring)


@dataclass(frozen=True, slots=True)
class CompletionSite:
    """The cursor's grammar position, expected type and surrounding text."""

    prefix: Prefix
    visible: Mapping[str, int]
    expected_type: int | None
    expected_role: str | None
    edit_range: types.Range
    expression_position: bool
    statement_position: bool
    event_position: bool
    existing_parentheses: bool
    existing_statement_suffix: bool
    following: Token | None
