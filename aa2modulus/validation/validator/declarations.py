"""Suggest a module global for a variable the module never declares.

Modules are standalone, so a module must declare every global it reads.
Declaring the missing global makes the module compile on its own.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from ...core.diagnostics import SourceFix
from ...core.locations import SourceSpan
from ...core.source_names import is_source_name
from ...model.records import Module
from ...model.types import TypeId, ValueType

_ZERO = {
    ValueType.INT: "0",
    ValueType.BOOL: "false",
    ValueType.FLOAT: "0.0",
    ValueType.STRING: '""',
}


@dataclass(frozen=True, slots=True)
class DeclarationAnchor:
    """Where a new global goes: an empty span, and the text around the declaration."""

    span: SourceSpan
    before: str
    after: str


def declaration_anchor(
    module_span: SourceSpan | None,
    global_spans: Iterable[SourceSpan | None],
    trigger_spans: Iterable[SourceSpan | None],
) -> DeclarationAnchor | None:
    """After the last global, else before the first indented trigger of the module file."""

    if module_span is None:
        return None
    filename = module_span.filename
    globals_ = [span for span in global_spans if span is not None and span.filename == filename]
    if globals_:
        last = globals_[-1]
        line = last.end_line or last.start_line
        column = last.end_column
        if column is None:
            return None
        empty = SourceSpan(filename, line, column + 1, line, column)
        return DeclarationAnchor(empty, "\n" + " " * (last.start_column - 1), "")
    for span in trigger_spans:
        if span is not None and span.filename == filename and span.start_column > 1:
            column = span.start_column
            empty = SourceSpan(filename, span.start_line, column, span.start_line, column - 1)
            return DeclarationAnchor(empty, "", "\n\n" + " " * (column - 1))
    return None


def module_declaration_anchor(module: Module) -> DeclarationAnchor | None:
    return declaration_anchor(
        module.source_span,
        (item.source_span for item in module.globals),
        (item.source_span for item in module.triggers),
    )


def declaration_help(
    name: str,
    value_type: TypeId,
    anchor: DeclarationAnchor | None,
    protected: frozenset[str],
) -> tuple[str | None, tuple[SourceFix, ...]]:
    """Help naming the declaration, and the edit that inserts it when there is a place."""

    zero = _ZERO.get(ValueType(value_type)) if value_type in ValueType else None
    if zero is None or not name:
        return None, ()
    bare = is_source_name(name, allow_qualified=False) and name.casefold() not in protected
    written = name if bare else json.dumps(name, ensure_ascii=True)
    declaration = f"global {written}: {ValueType(value_type).name.lower()} = {zero};"
    help = f"declare it in this module: `{declaration}`"
    if anchor is None:
        return help, ()
    replacement = anchor.before + declaration + anchor.after
    return help, (SourceFix(f"Declare global '{name}'", anchor.span, replacement),)
