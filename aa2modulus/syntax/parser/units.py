"""Parse entry points: modules, units and libraries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from lark.exceptions import UnexpectedInput, VisitError

from ...context.limits import SourceLimits, resolve_source_limits
from ...core.locations import SourceSpan
from ..ast import SourceModule, SourceUnit
from ..limits import check_source_ast
from .engine import parse_source_tree
from .errors import SourceParseError, unexpected_error
from .transform.transformer import SourceTransformer


def parse_source_ast(
    source: str,
    *,
    filename: str = "<source>",
    source_limits: SourceLimits | None = None,
) -> SourceModule:
    """Parse unified source into a syntax-only Source AST."""

    with _syntax_errors(source, filename):
        limits = resolve_source_limits(source_limits)
        module = _transform(source, filename, limits)
        if isinstance(module, SourceUnit):
            _reject_unit_items(module, filename)
        if isinstance(module, SourceModule):
            check_source_ast(module, filename=filename, limits=limits)
            return module
        raise TypeError(f"expected source module after parsing, got {module!r}")


def parse_source_unit(
    source: str,
    *,
    filename: str = "<source>",
    source_limits: SourceLimits | None = None,
    kind: Literal["module", "library"] = "module",
) -> SourceUnit:
    """Parse a module or library and its source-owned definitions."""

    with _syntax_errors(source, filename):
        if kind not in ("module", "library"):
            raise ValueError("kind must be 'module' or 'library'")
        limits = resolve_source_limits(source_limits)
        parsed = _transform(source, filename, limits)
        if isinstance(parsed, SourceModule):
            check_source_ast(parsed, filename=filename, limits=limits)
            parsed = SourceUnit(parsed, source_span=parsed.source_span)
        if not isinstance(parsed, SourceUnit):
            raise TypeError(f"expected source unit after parsing, got {parsed!r}")
        check_source_ast(parsed, filename=filename, limits=limits)
        if parsed.module is not None and parsed.templates:
            span = parsed.templates[0].source_span or parsed.module.source_span
            raise _located(
                span,
                filename,
                "trigger templates are only allowed in library sources",
                "TEMPLATE_LIBRARY_ONLY",
            )
        if kind == "module" and parsed.module is None:
            raise _located(
                parsed.source_span, filename, "a module declaration is required", "MODULE_REQUIRED"
            )
        if kind == "library" and parsed.module is not None:
            raise _located(
                parsed.module.source_span,
                filename,
                "library sources cannot declare a module",
                "LIBRARY_MODULE",
            )
        return parsed


def parse_library_source(
    source: str,
    *,
    filename: str = "<source>",
    source_limits: SourceLimits | None = None,
) -> SourceUnit:
    """Parse a module-free library source unit."""

    return parse_source_unit(
        source,
        filename=filename,
        source_limits=source_limits,
        kind="library",
    )


@contextmanager
def _syntax_errors(source: str, filename: str) -> Iterator[None]:
    """Report Lark failures, and errors raised inside the transformer, as SourceParseError."""

    try:
        yield
    except SourceParseError:
        raise
    except VisitError as exc:
        if isinstance(exc.orig_exc, SourceParseError):
            raise exc.orig_exc from None
        raise
    except UnexpectedInput as exc:
        raise unexpected_error(exc, filename, source) from exc


def _transform(source: str, filename: str, limits: SourceLimits) -> object:
    tree = parse_source_tree(source, filename=filename, source_limits=limits)
    return SourceTransformer(filename).transform(tree)


def _located(span: SourceSpan | None, filename: str, message: str, code: str) -> SourceParseError:
    return SourceParseError(
        span.filename if span is not None else filename,
        span.start_line if span is not None else 1,
        span.start_column if span is not None else 1,
        message,
        code,
        source_span=span,
    )


def _reject_unit_items(unit: SourceUnit, filename: str) -> None:
    """A plain module parse accepts no unit-only items; report the first in this order."""

    unit_only = (
        (unit.templates, "trigger templates require parse_library_source", "TEMPLATE_LIBRARY_ONLY"),
        (unit.imports, "imports require parse_source_unit", "IMPORT_UNIT_REQUIRED"),
        (unit.constants, "top-level constants require parse_source_unit", "CONST_UNIT_REQUIRED"),
        (unit.macros, "macro definitions require parse_source_unit", "MACRO_UNIT_REQUIRED"),
    )
    for items, message, code in unit_only:
        if items:
            raise _located(items[0].source_span or unit.source_span, filename, message, code)
    if unit.module is None:
        raise _located(
            unit.source_span, filename, "a module declaration is required", "MODULE_REQUIRED"
        )
    if unit.allows:
        span = unit.allows[0].source_span
        raise _located(
            span, filename, "@allow attributes require parse_source_unit", "ALLOW_UNIT_REQUIRED"
        )
