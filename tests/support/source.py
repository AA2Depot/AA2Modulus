"""Source parsing for tests: unified source to SIR without final validation."""

from __future__ import annotations

from typing import Any

from aa2modulus.context.operation import SourceContext
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
