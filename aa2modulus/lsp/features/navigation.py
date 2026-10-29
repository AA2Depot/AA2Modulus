"""Authoring responses from current compiler selections and authored syntax."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from lsprotocol import types

from ...core.locations import SourceSpan
from ...hir.symbols import SourceDeclaration
from ...language.documentation import builtin_description
from ...language.types import source_type_name
from ...model.native import ActionMetadata, ExpressionMetadata
from ...model.values import Value
from ...semantics.binding.constants import authoring_constants
from ...syntax import ast
from ...syntax.walk import walk_ast
from ..documentation.builtins import BuiltinDocumentation
from ..documentation.comments import declaration_documentation
from ..documentation.keywords import language_word_hover
from ..documentation.signatures import (
    constant_signature,
    declaration_signature,
    member_documentation,
    member_signature,
    metadata_signature,
    returns_text,
)
from ..protocol.positions import position_codec
from ..workspace.documents import Snapshot, SourceWorkspace
from .lookup import contains, declaration_span, reference_at


def hover(
    snapshot: Snapshot,
    position: types.Position,
    encoding: str,
) -> types.Hover | None:
    reference = reference_at(snapshot, position, encoding)
    text = ""
    span = None
    if reference is not None:
        span = reference.source_span
        metadata = reference.metadata
        form = reference.member_form
        policy = snapshot.analysis.context.source_policy
        if form is not None and isinstance(metadata, (ActionMetadata, ExpressionMetadata)):
            # A receiver-call member shows its explicit arguments and the native
            # target's description.
            text = f"```aa2m\n{member_signature(form, policy, receiver=True)}\n```\n\n"
            text += member_documentation(
                form,
                metadata,
                builtin_description(policy, metadata),
                returns=returns_text(policy, metadata),
            )
        elif metadata is not None:
            text = metadata_signature(reference.name, metadata, policy)
            text = f"```aa2m\n{text}\n```"
            if returns := returns_text(policy, metadata):
                text += f"\n\n{returns}"
            if description := builtin_description(policy, metadata):
                text += f"\n\n{description}"
        elif isinstance(reference.declaration, ast.SourceConstant):
            text = _documented_declaration(reference.declaration, snapshot, reference.value)
        elif reference.declaration is not None:
            text = _documented_declaration(reference.declaration, snapshot)
        elif reference.type is not None:
            text = f"{reference.name}: {source_type_name(reference.type)}"
    else:
        codec = position_codec(snapshot.document.text, encoding=encoding)
        for node in walk_ast(snapshot.analysis.ast or snapshot.authoring.ast):
            candidate = declaration_span(node)
            if (
                candidate is not None
                and candidate.filename == snapshot.document.filename
                and contains(codec, candidate, position)
                and (text := _documented_declaration(node, snapshot))
            ):
                span = candidate
                break
    if not text or span is None:
        return language_word_hover(
            position_codec(snapshot.document.text, encoding=encoding), position
        )
    return types.Hover(
        types.MarkupContent(types.MarkupKind.Markdown, text),
        range=position_codec(snapshot.document.text, encoding=encoding).range(span),
    )


def _documented_declaration(node: object, snapshot: Snapshot, value: Value | None = None) -> str:
    if isinstance(node, ast.SourceConstant):
        if value is None:
            unit = snapshot.analysis.ast or snapshot.authoring.ast
            value = _constant_value(unit, node, snapshot)
        text = constant_signature(node, value)
    else:
        text = declaration_signature(node)
    if not text:
        return ""
    description = declaration_documentation(node, snapshot.texts)
    return f"```aa2m\n{text}\n```" + (f"\n\n{description}" if description else "")


def _constant_value(
    unit: ast.SourceUnit | None, node: ast.SourceConstant, snapshot: Snapshot
) -> Value | None:
    """Resolve a declaration's value through the editor binder; None when unresolved."""

    if unit is None:
        return None
    composed = snapshot.authoring.unit or unit
    try:
        top, module = authoring_constants(composed, snapshot.analysis.context)
    except Exception:  # hover must not fail on partial source
        return None
    return next((item.value for item in (*top, *module) if item.declaration == node), None)


_FILE_START = types.Range(types.Position(0, 0), types.Position(0, 0))


def import_targets(snapshot: Snapshot) -> list[tuple[SourceSpan, str]]:
    """The path token and target file of each import in the document that was read."""

    unit = snapshot.analysis.ast or snapshot.authoring.ast
    if unit is None:
        return []
    targets: dict[SourceSpan, str] = {}
    for edge in (*snapshot.analysis.dependencies, *snapshot.authoring.dependencies):
        span = edge.source_span
        if span is None or span.filename != snapshot.document.filename:
            continue
        # Match only the authored path token, not the import keyword or semicolon.
        path_span = next(
            (item.path_span for item in unit.imports if item.source_span == span), None
        )
        if path_span is not None and edge.identity in snapshot.texts:
            targets.setdefault(path_span, edge.identity)
    return list(targets.items())


def document_links(
    snapshot: Snapshot, encoding: str, uri_for: Callable[[str], str]
) -> list[types.DocumentLink]:
    codec = position_codec(snapshot.document.text, encoding=encoding)
    return [
        types.DocumentLink(codec.range(path_span), target=uri_for(identity))
        for path_span, identity in import_targets(snapshot)
    ]


def definition(
    snapshot: Snapshot,
    position: types.Position,
    encoding: str,
    workspace: SourceWorkspace,
    *,
    documentation: BuiltinDocumentation | None = None,
) -> list[types.Location]:
    codec = position_codec(snapshot.document.text, encoding=encoding)
    for path_span, identity in import_targets(snapshot):
        if contains(codec, path_span, position):
            return [types.Location(workspace.uri_for(identity), _FILE_START)]
    reference = reference_at(snapshot, position, encoding)
    if reference is None:
        return []
    if reference.metadata is not None and documentation is not None:
        target = documentation.location(reference.metadata)
        return [target] if target is not None else []
    if reference.declaration is None:
        return []
    span = declaration_span(reference.declaration)
    if span is None or span.filename not in snapshot.texts:
        return []
    return [
        types.Location(
            workspace.uri_for(span.filename, root=snapshot.document),
            position_codec(snapshot.texts[span.filename], encoding=encoding).range(span),
        )
    ]


def document_symbols(snapshot: Snapshot, encoding: str) -> list[types.DocumentSymbol]:
    unit = snapshot.analysis.ast or snapshot.authoring.ast
    if unit is None:
        return []
    codec = position_codec(snapshot.document.text, encoding=encoding)

    def symbol(
        node: object, name: str, kind: types.SymbolKind, children: list[types.DocumentSymbol]
    ) -> types.DocumentSymbol | None:
        span = getattr(node, "source_span", None)
        selection = declaration_span(node)
        if span is None or selection is None or span.filename != snapshot.document.filename:
            return None
        return types.DocumentSymbol(
            name,
            kind,
            codec.range(span),
            codec.range(selection),
            detail=declaration_signature(node),
            children=children or None,
        )

    def variables(nodes: tuple[SourceDeclaration, ...]) -> list[types.DocumentSymbol]:
        return [
            item
            for node in nodes
            if (item := symbol(node, node.name, types.SymbolKind.Variable, [])) is not None
        ]

    def constants(nodes: tuple[ast.SourceConstant, ...]) -> list[types.DocumentSymbol]:
        return [
            item
            for node in nodes
            if (item := symbol(node, node.name, types.SymbolKind.Constant, [])) is not None
        ]

    result = constants(unit.constants)
    for macro in unit.macros:
        item = symbol(macro, macro.name, types.SymbolKind.Function, variables(macro.parameters))
        if item is not None:
            result.append(item)
    for template in unit.templates:
        item = symbol(
            template,
            template.name,
            types.SymbolKind.Event,
            variables((*template.slots, *template.trigger.locals)),
        )
        if item is not None:
            result.append(item)
    if unit.module is not None:
        children = [*variables(unit.module.globals), *constants(unit.module.constants)]
        for trigger in unit.module.triggers:
            item = symbol(
                trigger,
                trigger.name or trigger.template
                if isinstance(trigger, ast.SourceTriggerImport)
                else trigger.name,
                types.SymbolKind.Event,
                variables(trigger.locals) if isinstance(trigger, ast.SourceTrigger) else [],
            )
            if item is not None:
                children.append(item)
        item = symbol(unit.module, unit.module.name, types.SymbolKind.Module, children)
        if item is not None:
            result.append(item)
    return result


def workspace_symbols(
    snapshots: Iterable[Snapshot], query: str, *, encoding: str
) -> list[types.WorkspaceSymbol]:
    """Top-level and module-level declarations whose names contain ``query``.

    Matching ignores case; an exact name ranks first, then a prefix, then any
    other match, each ordered by file and position.
    """

    needle = query.casefold()
    found: list[tuple[tuple[int, str, int, int], types.WorkspaceSymbol]] = []
    for snapshot in snapshots:
        for top in document_symbols(snapshot, encoding):
            entries: list[tuple[types.DocumentSymbol, str | None]] = [(top, None)]
            if top.kind == types.SymbolKind.Module:
                entries += [(child, top.name) for child in top.children or ()]
            for item, container in entries:
                name = item.name.casefold()
                if needle not in name:
                    continue
                rank = 0 if name == needle else 1 if name.startswith(needle) else 2
                start = item.selection_range.start
                found.append(
                    (
                        (rank, snapshot.document.filename, start.line, start.character),
                        types.WorkspaceSymbol(
                            types.Location(snapshot.document.uri, item.selection_range),
                            item.name,
                            item.kind,
                            container_name=container,
                        ),
                    )
                )
    found.sort(key=lambda pair: pair[0])
    return [symbol for _, symbol in found]
