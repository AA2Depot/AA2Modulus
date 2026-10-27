"""Source helpers for tests: parsing without final validation, byte comparison, fixes."""

from __future__ import annotations

from typing import Any

from aa2modulus.app.compile import compile_source
from aa2modulus.context.operation import SourceContext
from aa2modulus.core.diagnostics import SourceFix
from aa2modulus.model.records import Module
from aa2modulus.pipeline.analysis import analyze_source


def parse_module(source: str, *, context: SourceContext | None = None, **inputs: Any) -> Module:
    """Parse, bind, and lower ``source``; ``inputs`` are ``SourceContext.resolve`` arguments."""

    operation = SourceContext.resolve(context, **inputs)
    analysis = analyze_source(source, context=operation, validate=False)
    if analysis.failure is not None:
        raise analysis.failure
    assert analysis.module is not None
    return analysis.module


def module_source(body: str = "", items: str = "", *, event: str = "CARD_ADDED") -> str:
    """A module with one trigger on ``event``; ``items`` are module items before the trigger."""

    return f'module "M" {{ {items} trigger "T" {{ on {event}; {body} }} }}'


def multiline_module(body: str) -> str:
    """A formatted module whose trigger declares ``y`` and then holds ``body``.

    ``body`` starts on line 5, column 5, so diagnostic positions can be written by hand.
    """

    return (
        'module "m" {\n  trigger "t" {\n    on CARD_ADDED;\n    let y: int = 1;\n    '
        + body
        + "\n  }\n}\n"
    )


def assert_same_binary(source: str, expected: str, **inputs: Any) -> bytes:
    """Assert both sources compile to the same bytes and return them.

    ``inputs`` are ``compile_source`` keyword arguments for both compilations.
    """

    binary = compile_source(expected, **inputs)
    assert compile_source(source, **inputs) == binary
    return binary


def apply_fix(source: str, fix: SourceFix) -> str:
    """``source`` with the edit of ``fix`` applied; the span end is inclusive."""

    span = fix.span
    assert span.end_line is not None and span.end_column is not None
    lines = source.splitlines(keepends=True)

    def offset(line: int, column: int) -> int:
        return sum(len(item) for item in lines[: line - 1]) + column - 1

    start = offset(span.start_line, span.start_column)
    end = offset(span.end_line, span.end_column) + 1
    return source[:start] + fix.replacement + source[end:]
