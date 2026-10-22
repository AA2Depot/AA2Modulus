"""Map command diagnostics into the texts a command read."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from ...core.diagnostics import Diagnostic
from ...core.locations import SourceSpan
from ..protocol.diagnostics import with_details
from ..protocol.positions import PositionCodec, position_codec
from ..workspace.documents import Document
from .results import CommandDiagnostic, CommandRange, CommandRelated

if TYPE_CHECKING:
    from ..server.app import AA2LanguageServer


@dataclass(slots=True)
class Locator:
    """Map diagnostics into the texts a command read, in the negotiated encoding.

    ``uri_for`` names source documents; without it the texts are recovered
    source, which has no URI until the client opens it.
    """

    texts: Mapping[str, str]
    encoding: str
    uri_for: Callable[[str], str] | None = None
    codecs: dict[str, PositionCodec] = field(default_factory=dict)

    def range(self, span: SourceSpan) -> CommandRange | None:
        text = self.texts.get(span.filename)
        if text is None:
            return None
        codec = self.codecs.get(span.filename)
        if codec is None:
            codec = self.codecs[span.filename] = position_codec(text, encoding=self.encoding)
        value = codec.range(span)
        return {
            "start": {"line": value.start.line, "character": value.start.character},
            "end": {"line": value.end.line, "character": value.end.character},
        }

    def entry(self, item: Diagnostic) -> CommandDiagnostic:
        result: CommandDiagnostic = {
            "severity": item.severity,
            "message": with_details(str(item), item),
            "code": item.code,
            "detail": with_details(item.message, item),
        }
        span = item.source_span
        if span is None and not item.is_binary_only:
            span = SourceSpan(item.filename, item.line, item.column)
        located = self.range(span) if span is not None else None
        if span is None or located is None:
            return result
        if self.uri_for is None:
            result["target"] = "recovered"
        else:
            result["target"] = "source"
            result["uri"] = self.uri_for(span.filename)
        result["range"] = located
        related: list[CommandRelated] = []
        for note in item.related:
            if (note_range := self.range(note.span)) is None:
                continue
            entry: CommandRelated = {"range": note_range, "message": note.message}
            if self.uri_for is not None:
                entry["uri"] = self.uri_for(note.span.filename)
            related.append(entry)
        if related:
            result["related"] = related
        return result


def command_diagnostics(
    items: tuple[Diagnostic, ...], *, locator: Locator | None = None
) -> list[CommandDiagnostic]:
    locator = locator or Locator({}, "utf-16")
    return [locator.entry(item) for item in items]


def source_locator(
    server: AA2LanguageServer, document: Document, texts: Mapping[str, str]
) -> Locator:
    return Locator(texts, server.encoding, partial(server.sources.uri_for, root=document))
