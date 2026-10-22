"""Source resource budgets and the located error raised when one is exceeded."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, fields, is_dataclass
from typing import NoReturn

from ..core.diagnostics import Diagnostic
from ..core.locations import SourceSpan


@dataclass(frozen=True, slots=True)
class SourceLimits:
    """Source stage and aggregate composition budgets, with inclusive bounds.

    Characters are Unicode code points. Parse nodes include trees and tokens;
    AST/HIR nodes include syntax records, excluding spans and registry records.
    Syntax depth counts tree/record levels, starting at one. Nesting depth counts
    statements and expressions (including raw expressions) on a path, excluding
    groups and payload records such as SourceRawParameters/BoundRawParameters.

    Depth options have supported ceilings because binding, lowering, and binary
    processing still recurse. Size and node limits may be raised without a cap.
    Macro preparation and instantiation share an independent aggregate node-work
    bound. Expression binding has a separate operation-wide work bound; failed
    overload trials consume it. Definition call depth includes the root and also bounds
    empty bodies. Template preparation/instantiation shares that work bound. Binding
    collects at most max_binding_errors independent errors, then stops with one summary
    error. A failed parse reports at most max_syntax_errors syntax errors the same way.
    Library graphs additionally cap unique imported files, longest edge depth, total
    characters (including root text), and retained AST nodes under max_nodes.
    """

    max_source_chars: int = 4_194_304
    max_nodes: int = 200_000
    max_syntax_depth: int = 256
    max_nesting_depth: int = 64
    max_expansion_nodes: int = 200_000
    max_binding_work: int = 200_000
    max_binding_errors: int = 100
    max_syntax_errors: int = 25
    max_macro_depth: int = 64
    max_import_files: int = 128
    max_import_depth: int = 32
    max_total_source_chars: int = 16_777_216

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field.name} must be an integer")
            if value < 0:
                raise ValueError(f"{field.name} must be nonnegative")
        if self.max_binding_errors < 1:
            raise ValueError("max_binding_errors must be at least 1")
        if self.max_syntax_errors < 1:
            raise ValueError("max_syntax_errors must be at least 1")
        if self.max_syntax_depth > 512:
            raise ValueError("max_syntax_depth cannot exceed the supported ceiling of 512")
        if self.max_nesting_depth > 128:
            raise ValueError("max_nesting_depth cannot exceed the supported ceiling of 128")
        if self.max_macro_depth > 128:
            raise ValueError("max_macro_depth cannot exceed the supported ceiling of 128")


class SourceLimitError(ValueError):
    """A located source-budget failure, separate from configuration errors."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


_DEFAULT_LIMITS = SourceLimits()


def resolve_source_limits(value: SourceLimits | None) -> SourceLimits:
    if value is None:
        return _DEFAULT_LIMITS
    return value


def span_diagnostic(filename: str, span: SourceSpan | None, code: str, message: str) -> Diagnostic:
    """An error at ``span``, or at the start of ``filename`` when nothing is located."""

    return Diagnostic(
        span.filename if span is not None else filename,
        span.start_line if span is not None else 1,
        span.start_column if span is not None else 1,
        "error",
        code,
        message,
        related=span.related if span is not None else (),
        source_span=span,
    )


def limit_error(filename: str, span: SourceSpan | None, code: str, message: str) -> NoReturn:
    raise SourceLimitError(span_diagnostic(filename, span, code, message))


def record_children(node: object) -> Iterator[object]:
    if not is_dataclass(node) or isinstance(node, type):
        raise TypeError("source budget nodes must be dataclass instances")
    for field in fields(node):
        if field.name != "source_span":
            yield getattr(node, field.name)


def check_records(
    module: object,
    *,
    filename: str,
    limits: SourceLimits,
    phase: str,
    node_types: tuple[type[object], ...],
    nested_types: tuple[type[object], ...],
) -> None:
    """Walk dataclass records iteratively, enforcing node, depth and nesting budgets.

    Only instances of ``node_types`` count; ``nested_types`` add one nesting level.
    """

    stack: list[tuple[Iterator[object], int, int, SourceSpan | None]] = [
        (iter((module,)), 1, 0, None)
    ]
    count = 0
    while stack:
        children, depth, nesting, parent_span = stack[-1]
        try:
            node = next(children)
        except StopIteration:
            stack.pop()
            continue
        if isinstance(node, tuple):
            stack.append((iter(node), depth, nesting, parent_span))
            continue
        if not isinstance(node, node_types):
            continue
        candidate_span = getattr(node, "source_span", None)
        span = candidate_span if isinstance(candidate_span, SourceSpan) else parent_span
        count += 1
        if count > limits.max_nodes:
            limit_error(
                filename,
                span,
                "SOURCE_NODE_LIMIT",
                f"{phase} exceeds the node limit of {limits.max_nodes}",
            )
        if depth > limits.max_syntax_depth:
            limit_error(
                filename,
                span,
                "SOURCE_DEPTH_LIMIT",
                f"{phase} exceeds the syntax depth limit of {limits.max_syntax_depth}",
            )
        child_nesting = nesting + int(isinstance(node, nested_types))
        if child_nesting > limits.max_nesting_depth:
            limit_error(
                filename,
                span,
                "SOURCE_NESTING_LIMIT",
                f"{phase} exceeds the statement/expression nesting limit of "
                f"{limits.max_nesting_depth}",
            )
        stack.append((record_children(node), depth + 1, child_nesting, span))
