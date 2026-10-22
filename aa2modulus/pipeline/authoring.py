"""Fresh, bounded Source AST views for unfinished editor documents.

Recovery (``recovery.py``) feeds the production grammar twice. The first pass has
tree callbacks disabled and retains shallow checkpoints only at completed syntax
boundaries. The second pass builds the production tree from retained positioned
tokens. Neither recovered syntax nor its references enters the compiler pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, cast

from lark import Token, Tree
from lark.exceptions import UnexpectedInput, VisitError

from ..context.limits import SourceLimitError, SourceLimits
from ..context.operation import SourceContext
from ..core.locations import line_column
from ..hir.symbols import BoundReference
from ..semantics.binding.authoring import bind_authoring_references
from ..syntax import ast as source_ast
from ..syntax.imports import (
    SourceDependency,
    SourceImportError,
    check_source_graph_text,
    resolve_source_imports,
)
from ..syntax.limits import check_source_ast, check_source_tree
from ..syntax.parser.engine import shared_parser
from ..syntax.parser.errors import SourceParseError, unexpected_error
from ..syntax.parser.transform.transformer import SourceTransformer
from ..syntax.recovery import MAX_FAULTS, fault_limit, lex_tokens, retain_tokens
from .analysis import SourceAnalysis, SourceFailure


@dataclass(frozen=True, slots=True)
class EditorPrefix:
    tokens: tuple[Token, ...]
    expected: frozenset[str]
    recovered: bool = False


@dataclass(frozen=True, slots=True)
class SourceAuthoring:
    """Current authored/composed syntax and successful binder selections."""

    ast: source_ast.SourceUnit | None = None
    unit: source_ast.SourceUnit | None = None
    references: tuple[BoundReference, ...] = ()
    dependencies: tuple[SourceDependency, ...] = ()
    failure: SourceFailure | None = None
    source: str = ""


def editor_prefix(source: str, context: SourceContext) -> EditorPrefix:
    """Return the grammar state at EOF while recovering only earlier faults."""

    tokens, faults = lex_tokens(source, context, cursor=True)
    machine, retained, _, _, faults, _ = retain_tokens(tokens, context, faults)
    return EditorPrefix(tuple(retained), frozenset(machine.accepts()), faults > 0)


def parse_editor_unit(
    source: str, context: SourceContext, *, kind: Literal["module", "library"] = "module"
) -> source_ast.SourceUnit:
    """Drop unfinished items and close existing containers at the real EOF."""

    tokens, faults = lex_tokens(source, context)
    machine, retained, checkpoint, checkpoint_count, faults, _ = retain_tokens(
        tokens, context, faults
    )
    if "$END" not in machine.accepts():
        machine = checkpoint.copy(deepcopy_values=False)
        del retained[checkpoint_count:]
        faults += 1
        if faults > MAX_FAULTS:
            raise fault_limit(context.filename)
    line, column = line_column(source, len(source))
    for _ in range(context.source_limits.max_syntax_depth + 1):
        accepted = machine.accepts()
        if "$END" in accepted:
            break
        if "RBRACE" not in accepted:
            try:
                machine.feed_eof()
            except UnexpectedInput as exc:
                raise unexpected_error(exc, context.filename, source) from exc
            raise SourceParseError(context.filename, line, column, "unfinished editor syntax")
        close = Token(
            "RBRACE",
            "}",
            start_pos=len(source),
            line=line,
            column=column,
            end_line=line,
            end_column=column + 1,
            end_pos=len(source),
        )
        machine.feed_token(close)
        retained.append(close)
    else:
        raise fault_limit(context.filename)
    # Checkpoints never retain parse trees. Build the one real tree now, using
    # original token positions rather than reparsing shifted/replaced source.
    parsed = shared_parser().parse_interactive()
    try:
        for token in retained:
            parsed.feed_token(token)
        tree = cast(Tree[Token], parsed.feed_eof())
        check_source_tree(tree, filename=context.filename, limits=context.source_limits)
        transformed = SourceTransformer(context.filename).transform(tree)
    except UnexpectedInput as exc:
        raise unexpected_error(exc, context.filename, source) from exc
    except VisitError as exc:
        if isinstance(exc.orig_exc, SourceParseError):
            raise exc.orig_exc from exc
        raise
    if isinstance(transformed, source_ast.SourceModule):
        transformed = source_ast.SourceUnit(transformed, source_span=transformed.source_span)
    if not isinstance(transformed, source_ast.SourceUnit):
        raise TypeError("editor parser must produce a SourceUnit")
    if kind == "library" and transformed.module is not None:
        raise SourceParseError(context.filename, 1, 1, "library sources cannot declare a module")
    if transformed.module is not None and transformed.templates:
        raise SourceParseError(context.filename, 1, 1, "trigger templates are library-only")
    check_source_ast(transformed, filename=context.filename, limits=context.source_limits)
    return transformed


def analyze_authoring(
    source: str,
    context: SourceContext,
    *,
    analysis: SourceAnalysis | None = None,
    source_kind: Literal["module", "library"] = "module",
) -> SourceAuthoring:
    """Recover current syntax and imports without lowering or compilation."""

    if analysis is not None and isinstance(analysis.failure, SourceLimitError):
        return SourceAuthoring(failure=analysis.failure, source=source)
    if analysis is not None and analysis.source == source and analysis.composed_ast is not None:
        # Parsing and imports succeeded, so their trees serve the editor view
        # as they are; only binding may have failed.
        if analysis.bound is not None:
            references = analysis.bound.references
        else:
            try:
                references = bind_authoring_references(analysis.composed_ast, context)
            except SourceLimitError as exc:
                return SourceAuthoring(
                    dependencies=analysis.dependencies, failure=exc, source=source
                )
        return SourceAuthoring(
            analysis.ast, analysis.composed_ast, references, analysis.dependencies, source=source
        )
    root = None
    composed = None
    dependencies: list[SourceDependency] = []
    libraries: list[source_ast.SourceUnit] = []
    failure: SourceFailure | None = None

    def library_parser(text: str, identity: str, limits: SourceLimits) -> source_ast.SourceUnit:
        library = parse_editor_unit(
            text, replace(context, filename=identity, source_limits=limits), kind="library"
        )
        libraries.append(library)
        return library

    try:
        check_source_graph_text(source, context)
        root = analysis.ast if analysis is not None and analysis.source == source else None
        root = root or parse_editor_unit(source, context, kind=source_kind)
        composed = resolve_source_imports(
            root,
            context,
            root_chars=len(source),
            dependencies=dependencies,
            library_parser=library_parser,
        )
    except SourceLimitError as exc:
        # A failed aggregate/depth budget must not expose a partial oversized view.
        return SourceAuthoring(dependencies=tuple(dependencies), failure=exc, source=source)
    except (SourceParseError, SourceImportError) as exc:
        failure = exc
        if root is not None:
            composed = replace(
                root,
                macros=(*root.macros, *(item for unit in libraries for item in unit.macros)),
                templates=(
                    *root.templates,
                    *(item for unit in libraries for item in unit.templates),
                ),
                constants=(
                    *root.constants,
                    *(item for unit in libraries for item in unit.constants),
                ),
                imports=(),
            )
    try:
        references = bind_authoring_references(composed, context) if composed is not None else ()
    except SourceLimitError as exc:
        return SourceAuthoring(dependencies=tuple(dependencies), failure=exc, source=source)
    return SourceAuthoring(root, composed, references, tuple(dependencies), failure, source)
