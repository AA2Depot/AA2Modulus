"""Explicit, bounded, operation-local source library resolution."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, cast

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

from ..context.limits import SourceLimitError, SourceLimits, span_diagnostic
from ..context.operation import SourceContext
from ..context.resolver import FileSourceResolver, SourceResolver
from ..core.diagnostics import Diagnostic
from ..core.locations import RelatedLocation, SourceSpan, with_related
from . import ast
from .limits import AST_NODES, check_source_ast
from .parser.errors import SourceParseError
from .parser.units import parse_library_source
from .walk import walk_ast


class SourceImportError(ValueError):
    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


@dataclass(frozen=True, slots=True)
class SourceDependency:
    """A resolved import edge, retained even when reading its target fails."""

    identity: str
    importer: str | None
    source_span: SourceSpan | None


def _fail(
    filename: str, span: SourceSpan | None, code: str, message: str, *, limit: bool = False
) -> NoReturn:
    diagnostic = span_diagnostic(filename, span, code, message)
    raise (SourceLimitError if limit else SourceImportError)(diagnostic)


def _origins(unit: ast.SourceUnit, notes: tuple[RelatedLocation, ...]) -> ast.SourceUnit:
    """Annotate the existing AST iteratively, without consuming Python recursion."""

    stack: list[tuple[object, bool]] = [(unit, False)]
    values: list[object] = []
    while stack:
        value, ready = stack.pop()
        if isinstance(value, tuple):
            if not ready:
                stack.append((value, True))
                stack.extend((item, False) for item in reversed(value))
            else:
                count = len(value)
                result = tuple(values[-count:]) if count else ()
                if count:
                    del values[-count:]
                values.append(result)
        elif isinstance(value, AST_NODES):
            names = tuple(item.name for item in fields(value) if item.name != "source_span")
            if not ready:
                stack.append((value, True))
                stack.extend((getattr(value, name), False) for name in reversed(names))
            else:
                count = len(names)
                updates = dict(zip(names, values[-count:], strict=True)) if count else {}
                if count:
                    del values[-count:]
                if hasattr(value, "source_span"):
                    updates["source_span"] = with_related(value.source_span, notes)
                values.append(replace(cast("DataclassInstance", value), **updates))
        else:
            values.append(value)
    return cast(ast.SourceUnit, values[0])


@dataclass(slots=True)
class _Frame:
    identity: str | None
    imports: Iterator[ast.SourceImport]
    height: int = 0


def check_source_graph_text(source: str, operation: SourceContext) -> None:
    if len(source) > operation.source_limits.max_total_source_chars:
        _fail(
            operation.filename,
            None,
            "IMPORT_SIZE_LIMIT",
            "source graph exceeds the aggregate character limit",
            limit=True,
        )


def resolve_source_imports(
    unit: ast.SourceUnit,
    operation: SourceContext,
    *,
    root_chars: int = 0,
    dependencies: list[SourceDependency] | None = None,
    library_parser: Callable[[str, str, SourceLimits], ast.SourceUnit] | None = None,
) -> ast.SourceUnit:
    """Compose unique libraries into one explicit transitive export namespace."""

    limits = operation.source_limits
    if root_chars > limits.max_total_source_chars:
        _fail(
            operation.filename,
            unit.source_span,
            "IMPORT_SIZE_LIMIT",
            "source graph exceeds the aggregate character limit",
            limit=True,
        )
    if not unit.imports:
        return unit
    resolver = _resolver(unit, operation)
    total_chars = root_chars
    total_nodes = sum(1 for _ in walk_ast(unit))
    macros = list(unit.macros)
    templates = list(unit.templates)
    constants = list(unit.constants)
    allows = list(unit.allows)
    state: dict[str, int] = {}
    heights: dict[str, int] = {}
    stack = [_Frame(None, iter(unit.imports))]
    while stack:
        frame = stack[-1]
        edge = next(frame.imports, None)
        if edge is None:
            _close_frame(stack, state, heights)
            continue
        span = edge.source_span
        identity = _resolve_edge(resolver, edge, frame.identity, operation)
        if dependencies is not None:
            dependencies.append(SourceDependency(identity, frame.identity, span))
        _check_edge(stack, identity, span, state, heights, operation)
        if state.get(identity) == 2:
            frame.height = max(frame.height, 1 + heights[identity])
            continue
        if len(state) >= limits.max_import_files:
            _fail(
                operation.filename,
                span,
                "IMPORT_FILE_LIMIT",
                "source graph exceeds the unique library limit",
                limit=True,
            )
        text = _read_library(
            resolver, identity, span, operation, limits.max_total_source_chars - total_chars
        )
        total_chars += len(text)
        notes = (
            ()
            if span is None
            else (RelatedLocation(span, f"library {edge.path!r} imported here"), *span.related)
        )
        library = _parse_library(text, identity, limits, notes, library_parser)
        total_nodes += sum(1 for _ in walk_ast(library))
        if total_nodes > limits.max_nodes:
            _fail(
                operation.filename,
                span,
                "SOURCE_NODE_LIMIT",
                "source graph exceeds the aggregate AST node limit",
                limit=True,
            )
        library = _origins(library, notes)
        macros.extend(library.macros)
        templates.extend(library.templates)
        constants.extend(library.constants)
        allows.extend(library.allows)
        state[identity] = 1
        stack.append(_Frame(identity, iter(library.imports)))
    composed = replace(
        unit,
        macros=tuple(macros),
        templates=tuple(templates),
        constants=tuple(constants),
        allows=tuple(allows),
        imports=(),
    )
    check_source_ast(composed, filename=operation.filename, limits=limits)
    return composed


def _close_frame(stack: list[_Frame], state: dict[str, int], heights: dict[str, int]) -> None:
    """Finish the top library: record its import height for later depth checks."""

    frame = stack.pop()
    if frame.identity is not None:
        state[frame.identity] = 2
        heights[frame.identity] = frame.height
    if stack:
        stack[-1].height = max(stack[-1].height, 1 + frame.height)


def _check_edge(
    stack: list[_Frame],
    identity: str,
    span: SourceSpan | None,
    state: dict[str, int],
    heights: dict[str, int],
    operation: SourceContext,
) -> None:
    """Reject an import that closes a cycle or makes the import chain too deep."""

    if state.get(identity) == 1:
        chain = " -> ".join([item.identity or operation.filename for item in stack] + [identity])
        _fail(operation.filename, span, "IMPORT_CYCLE", f"cyclic source imports: {chain}")
    depth = len(stack)
    if depth + heights.get(identity, 0) > operation.source_limits.max_import_depth:
        _fail(
            operation.filename,
            span,
            "IMPORT_DEPTH_LIMIT",
            "source import depth exceeds the limit",
            limit=True,
        )


def _resolver(unit: ast.SourceUnit, operation: SourceContext) -> SourceResolver:
    resolver = operation.source_resolver
    if resolver is not None:
        return resolver
    if operation.import_base is None:
        _fail(
            operation.filename,
            unit.imports[0].source_span,
            "IMPORT_RESOLVER_REQUIRED",
            "source imports require an explicit import_base or source_resolver",
        )
    return FileSourceResolver(operation.import_base)


def _resolve_edge(
    resolver: SourceResolver,
    edge: ast.SourceImport,
    importer: str | None,
    operation: SourceContext,
) -> str:
    """The canonical identity of an imported ``.aa2mi`` library."""

    span = edge.source_span
    if not edge.path or "\x00" in edge.path or Path(edge.path).suffix != ".aa2mi":
        _fail(operation.filename, span, "IMPORT_PATH", "imports require a .aa2mi library path")
    try:
        identity = resolver.resolve(edge.path, importer=importer)
    except (OSError, ValueError) as exc:
        _fail(operation.filename, span, "IMPORT_PATH", f"could not resolve {edge.path!r}: {exc}")
    if not identity:
        raise ValueError("source_resolver.resolve must return a non-empty identity")
    return identity


def _read_library(
    resolver: SourceResolver,
    identity: str,
    span: SourceSpan | None,
    operation: SourceContext,
    remaining: int,
) -> str:
    """Library text, at most ``remaining`` characters of the graph's aggregate budget."""

    read_limit = min(operation.source_limits.max_source_chars, remaining)
    try:
        text = resolver.read(identity, max_chars=read_limit)
    except UnicodeError:
        _fail(
            operation.filename,
            span,
            "IMPORT_ENCODING",
            f"library {identity!r} is not valid UTF-8 text",
        )
    except OSError as exc:
        _fail(
            operation.filename,
            span,
            "IMPORT_READ_ERROR",
            f"could not read library {identity!r}: {exc.strerror or exc}",
        )
    if len(text) > remaining:
        _fail(
            operation.filename,
            span,
            "IMPORT_SIZE_LIMIT",
            "source graph exceeds the aggregate character limit",
            limit=True,
        )
    return text


def _parse_library(
    text: str,
    identity: str,
    limits: SourceLimits,
    notes: tuple[RelatedLocation, ...],
    library_parser: Callable[[str, str, SourceLimits], ast.SourceUnit] | None,
) -> ast.SourceUnit:
    """Parse a library; its errors note where it was imported."""

    try:
        return (
            parse_library_source(text, filename=identity, source_limits=limits)
            if library_parser is None
            else library_parser(text, identity, limits)
        )
    except SourceParseError as exc:
        raise SourceImportError(replace(exc.to_diagnostic(), related=notes)) from exc
    except SourceLimitError as exc:
        raise SourceLimitError(
            replace(exc.diagnostic, related=(*exc.diagnostic.related, *notes))
        ) from exc
