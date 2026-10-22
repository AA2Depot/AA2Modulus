"""References and highlights for authored declarations.

A declaration is identified by its declaration span, which every analysis of
the same text agrees on. Its occurrences are that span plus every binder
reference selecting it, collected across the analyses in scope.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from lsprotocol import types

from ...core.locations import SourceSpan
from ...hir.symbols import SourceDeclaration
from ...syntax import ast
from ...syntax.walk import walk_ast
from ..protocol.positions import PositionCodec, position_codec
from ..workspace.documents import Snapshot
from .lookup import bound_references, contains, declaration_span, reference_at

_DECLARATIONS = (
    ast.SourceGlobal,
    ast.SourceLocal,
    ast.SourceParameter,
    ast.SourceMacro,
    ast.SourceTriggerTemplate,
    ast.SourceConstant,
)


@dataclass(frozen=True, slots=True)
class Target:
    """An authored declaration, identified by its declaration name span."""

    declaration: SourceDeclaration
    span: SourceSpan

    @property
    def name(self) -> str:
        return self.declaration.name

    @property
    def workspace_wide(self) -> bool:
        """Only saved ``.aa2mi`` libraries can be imported; other names are file-local."""

        filename = self.span.filename
        return not filename.startswith("untitled:") and Path(filename).suffix.lower() == ".aa2mi"


@dataclass(frozen=True, slots=True)
class Occurrence:
    span: SourceSpan
    write: bool = False
    declaration: bool = False


@dataclass(frozen=True, slots=True)
class Sites:
    """Syntactic roles of name spans that the reference list does not carry."""

    writes: frozenset[SourceSpan]
    loop_targets: frozenset[SourceSpan]
    unnamed_imports: frozenset[SourceSpan]
    slots: frozenset[SourceSpan]


def _unit(snapshot: Snapshot) -> ast.SourceUnit | None:
    return (
        snapshot.analysis.composed_ast
        or snapshot.authoring.unit
        or snapshot.analysis.ast
        or snapshot.authoring.ast
    )


def sites_of(snapshot: Snapshot) -> Sites:
    writes: set[SourceSpan] = set()
    loops: set[SourceSpan] = set()
    unnamed: set[SourceSpan] = set()
    slots: set[SourceSpan] = set()
    for node in walk_ast(_unit(snapshot)):
        if isinstance(node, (ast.SourceAssignment, ast.SourceFor)) and node.target_span:
            writes.add(node.target_span)
            if isinstance(node, ast.SourceFor):
                loops.add(node.target_span)
        elif isinstance(node, ast.SourceTriggerImport) and node.name is None and node.template_span:
            unnamed.add(node.template_span)
        elif isinstance(node, ast.SourceTriggerTemplate):
            slots.update(span for slot in node.slots if (span := declaration_span(slot)))
    return Sites(frozenset(writes), frozenset(loops), frozenset(unnamed), frozenset(slots))


def target_at(snapshot: Snapshot, position: types.Position, encoding: str) -> Target | None:
    """The authored declaration named at ``position``, from a use or the declaration."""

    reference = reference_at(snapshot, position, encoding)
    if reference is not None:
        if reference.declaration is None:
            return None
        span = declaration_span(reference.declaration)
        return Target(reference.declaration, span) if span is not None else None
    codec = position_codec(snapshot.document.text, encoding=encoding)
    for node in walk_ast(snapshot.analysis.ast or snapshot.authoring.ast):
        if not isinstance(node, _DECLARATIONS):
            continue
        span = declaration_span(node)
        if (
            span is not None
            and span.filename == snapshot.document.filename
            and contains(codec, span, position)
        ):
            return Target(node, span)
    return None


def occurrences(snapshots: Iterable[Snapshot], target: Target) -> dict[SourceSpan, Occurrence]:
    """The declaration and every use of ``target`` in the analyses that read its file."""

    found: dict[SourceSpan, Occurrence] = {}
    for snapshot in snapshots:
        if target.span.filename not in snapshot.texts:
            continue
        found.setdefault(target.span, Occurrence(target.span, write=True, declaration=True))
        sites: Sites | None = None
        for reference in bound_references(snapshot):
            span = reference.source_span
            if (
                span is None
                or span in found
                or reference.declaration is None
                or span.filename not in snapshot.texts
                or declaration_span(reference.declaration) != target.span
            ):
                continue
            sites = sites or sites_of(snapshot)
            found[span] = Occurrence(span, write=span in sites.writes)
    return found


def _order(span: SourceSpan) -> tuple[str, int, int]:
    return span.filename, span.start_line, span.start_column


def document_highlights(
    snapshot: Snapshot, position: types.Position, encoding: str
) -> list[types.DocumentHighlight]:
    target = target_at(snapshot, position, encoding)
    if target is None:
        return []
    codec = position_codec(snapshot.document.text, encoding=encoding)
    found = occurrences((snapshot,), target)
    return [
        types.DocumentHighlight(
            codec.range(span),
            types.DocumentHighlightKind.Write
            if found[span].write
            else types.DocumentHighlightKind.Read,
        )
        for span in sorted(found, key=_order)
        if span.filename == snapshot.document.filename
    ]


def reference_locations(
    snapshots: Sequence[Snapshot],
    target: Target,
    encoding: str,
    uri_for: Callable[[str], str],
    *,
    include_declaration: bool,
) -> list[types.Location]:
    texts: dict[str, str] = {}
    for snapshot in snapshots:
        for filename, text in snapshot.texts.items():
            texts.setdefault(filename, text)
    codecs: dict[str, PositionCodec] = {}
    result = []
    for span, item in sorted(
        occurrences(snapshots, target).items(), key=lambda pair: _order(pair[0])
    ):
        if item.declaration and not include_declaration:
            continue
        codec = codecs.get(span.filename)
        if codec is None:
            codec = codecs[span.filename] = position_codec(texts[span.filename], encoding=encoding)
        result.append(types.Location(uri_for(span.filename), codec.range(span)))
    return result
