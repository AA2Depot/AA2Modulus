"""Diagnostic location annotations shared by source and binary model nodes."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass, replace

PathPart = str | int


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """A one-based source location annotation."""

    filename: str
    start_line: int
    start_column: int
    end_line: int | None = None
    end_column: int | None = None
    related: tuple[RelatedLocation, ...] = field(
        default=(), compare=False, repr=False, kw_only=True
    )

    def __post_init__(self) -> None:
        if not self.filename:
            raise ValueError("source filename cannot be empty")
        if self.start_line < 1 or self.start_column < 1:
            raise ValueError("source locations are one-based")
        if self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line cannot precede start_line")
        if self.end_column is not None and self.end_column < 1:
            raise ValueError("end_column must be one-based")
        object.__setattr__(self, "related", tuple(self.related))


@dataclass(frozen=True, slots=True)
class RelatedLocation:
    """A diagnostic note attached to a source expansion origin."""

    span: SourceSpan
    message: str

    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError("related location messages cannot be empty")


def with_related(span: SourceSpan | None, notes: tuple[RelatedLocation, ...]) -> SourceSpan | None:
    """Retain a primary span and append flat, deterministic expansion notes."""

    if span is None:
        return None
    combined: list[RelatedLocation] = []
    for note in (*span.related, *notes):
        flat = RelatedLocation(replace(note.span, related=()), note.message)
        if flat not in combined:
            combined.append(flat)
    return replace(span, related=tuple(combined))


@dataclass(frozen=True, slots=True)
class BinaryLocation:
    """A node's byte offset and absolute structural path from the module root."""

    offset: int
    path: tuple[PathPart, ...] = ()

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("binary offsets cannot be negative")
        object.__setattr__(self, "path", tuple(self.path))


def source_span_index(
    root: object, root_path: tuple[PathPart, ...] = ("module",)
) -> dict[tuple[PathPart, ...], SourceSpan]:
    """Map the structural path of every model node with a source span to that span.

    Paths use model field names and tuple indexes, the same form as
    ``BinaryLocation.path`` and decoder/writer error paths.
    """

    index: dict[tuple[PathPart, ...], SourceSpan] = {}
    pending: list[tuple[object, tuple[PathPart, ...]]] = [(root, root_path)]
    while pending:
        node, path = pending.pop()
        if isinstance(node, tuple):
            pending.extend((item, (*path, position)) for position, item in enumerate(node))
        elif is_dataclass(node) and not isinstance(node, type):
            span = getattr(node, "source_span", None)
            if isinstance(span, SourceSpan):
                index.setdefault(path, span)
            for item in fields(node):
                if item.name not in {"source_span", "binary_location"}:
                    pending.append((getattr(node, item.name), (*path, item.name)))
    return index


def nearest_source_span(
    index: dict[tuple[PathPart, ...], SourceSpan], path: tuple[PathPart, ...]
) -> SourceSpan | None:
    """The span of the deepest indexed node on ``path``."""

    while path:
        span = index.get(path)
        if span is not None:
            return span
        path = path[:-1]
    return None


def line_column(source: str, offset: int) -> tuple[int, int]:
    """One-based line and column (in code points) of ``offset`` in ``source``."""

    return source.count("\n", 0, offset) + 1, offset - source.rfind("\n", 0, offset)
