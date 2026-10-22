"""Diagnostic rendering: ``human`` snippets, ``short`` lines, counts and output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TextIO

from ...core.diagnostics import Diagnostic, format_path
from ...core.locations import SourceSpan
from ...model.records import Module
from .breadcrumb import breadcrumb, unlocated_notes
from .snippets import SourceTexts, snippet_block
from .terminal import BLUE, BOLD, SEVERITY_STYLE, RenderOptions, paint


def _gutter_width(diagnostic: Diagnostic) -> int:
    numbers = [1]
    if not diagnostic.is_binary_only:
        numbers.append(_primary_span(diagnostic).start_line)
    numbers.extend(note.span.start_line for note in diagnostic.related)
    return len(str(max(numbers)))


def _primary_span(diagnostic: Diagnostic) -> SourceSpan:
    if diagnostic.source_span is not None:
        return diagnostic.source_span
    return SourceSpan(diagnostic.filename, diagnostic.line, diagnostic.column)


def render_diagnostic(
    diagnostic: Diagnostic,
    *,
    options: RenderOptions | None = None,
    sources: SourceTexts | Mapping[str, str] | None = None,
    module: Module | None = None,
) -> str:
    """Render one diagnostic in the requested format (no trailing newline)."""

    options = options or RenderOptions()
    if options.format == "short":
        return _render_short(diagnostic, options)
    texts = sources if isinstance(sources, SourceTexts) else SourceTexts(sources)
    color = options.color
    style = SEVERITY_STYLE[diagnostic.severity]
    width = _gutter_width(diagnostic)
    pad = " " * (width + 1)
    head = paint(f"{diagnostic.severity}[{diagnostic.code}]", color, BOLD, style)
    out = [f"{head}{paint(': ' + diagnostic.message, color, BOLD)}"]

    last_has_snippet = False
    extras: list[tuple[str, str]] = []
    notes = diagnostic.notes
    if diagnostic.is_binary_only:
        assert diagnostic.offset is not None
        arrow = paint("-->", color, BOLD, BLUE)
        out.append(f"{' ' * width}{arrow} {diagnostic.filename} (offset 0x{diagnostic.offset:X})")
        if diagnostic.path:
            crumb = breadcrumb(diagnostic.path, module=module, separator=options.separator)
            extras.append(("in", crumb))
            notes = unlocated_notes(diagnostic, crumb)
    else:
        block = snippet_block(_primary_span(diagnostic), texts, width, options, style)
        out.extend(block.lines)
        last_has_snippet = block.has_snippet
        if options.verbose and diagnostic.offset is not None:
            extras.append(("offset", f"0x{diagnostic.offset:X}"))
    if options.verbose and diagnostic.path:
        extras.append(("path", format_path(diagnostic.path)))

    for related in diagnostic.related:
        if last_has_snippet:
            out.append(f"{pad}{paint('|', color, BOLD, BLUE)}")
        out.append(f"{paint('note', color, BOLD)}{paint(': ' + related.message, color, BOLD)}")
        block = snippet_block(related.span, texts, width, options, BLUE)
        out.extend(block.lines)
        last_has_snippet = block.has_snippet

    tail: list[tuple[str, str]] = [("note", note) for note in notes]
    if diagnostic.help:
        tail.append(("help", diagnostic.help))
    tail.extend(extras)
    if tail and last_has_snippet:
        out.append(f"{pad}{paint('|', color, BOLD, BLUE)}")
    for label, text in tail:
        equals = paint("=", color, BOLD, BLUE)
        out.append(f"{pad}{equals} {paint(label + ':', color, BOLD)} {text}")
    return "\n".join(out)


def _render_short(diagnostic: Diagnostic, options: RenderOptions) -> str:
    text = str(diagnostic)
    if options.color:
        prefix = f"{diagnostic.location}: "
        label = f"{diagnostic.severity}[{diagnostic.code}]"
        if text.startswith(prefix + label):
            style = SEVERITY_STYLE[diagnostic.severity]
            text = prefix + paint(label, True, BOLD, style) + text[len(prefix) + len(label) :]
    if options.verbose:
        evidence = []
        if diagnostic.offset is not None:
            evidence.append(f"offset 0x{diagnostic.offset:X}")
        if diagnostic.path:
            evidence.append(f"path {format_path(diagnostic.path)}")
        if evidence:
            text += f"\n  evidence: {', '.join(evidence)}"
    return text


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def count_text(diagnostics: Sequence[Diagnostic]) -> str:
    """``2 errors, 1 warning``; empty when there are neither."""

    errors = sum(1 for item in diagnostics if item.severity == "error")
    warnings = sum(1 for item in diagnostics if item.severity == "warning")
    parts = []
    if errors:
        parts.append(_plural(errors, "error"))
    if warnings:
        parts.append(_plural(warnings, "warning"))
    return ", ".join(parts)


def render_diagnostics(
    diagnostics: Sequence[Diagnostic],
    *,
    options: RenderOptions | None = None,
    sources: SourceTexts | Mapping[str, str] | None = None,
    module: Module | None = None,
    summary: str | None = None,
) -> str:
    """Render all diagnostics plus an optional closing summary line."""

    options = options or RenderOptions()
    texts = sources if isinstance(sources, SourceTexts) else SourceTexts(sources)
    pieces = [
        render_diagnostic(item, options=options, sources=texts, module=module)
        for item in diagnostics
    ]
    separator = "\n\n" if options.format == "human" else "\n"
    text = separator.join(pieces)
    if summary:
        closing = paint(summary, options.color, BOLD)
        text = f"{text}{separator}{closing}" if text else closing
    return text


def write_diagnostics(
    diagnostics: Sequence[Diagnostic],
    stream: TextIO,
    options: RenderOptions,
    *,
    sources: SourceTexts | Mapping[str, str] | None = None,
    module: Module | None = None,
    summary: str | None = None,
) -> None:
    """Print diagnostics (and a summary) to ``stream``; nothing if both are empty."""

    text = render_diagnostics(
        diagnostics, options=options, sources=sources, module=module, summary=summary
    )
    if text:
        print(text, file=stream)
