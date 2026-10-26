"""Bare reserved words fail where they declare or target a value; the fix writes the quoted form."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import parse_and_validate_source
from aa2modulus.core.diagnostics import Diagnostic, SourceFix

QUOTE = 'quote the name: `"{w}"`'
READ = 'read it with `const("{w}")`'

# Module items, trigger body, help and fix replacement; `{w}` is the reserved word.
POSITIONS = (
    ("", "let {w}: int = 1;", QUOTE, '"{w}"'),
    ('global "{w}": int = 0;', "{w} = 2;", 'assign it with `variable("{w}")`', 'variable("{w}")'),
    ('global "{w}": int = 0;', "for {w} from 1 to 2 {{ }}", QUOTE, '"{w}"'),
    ("global {w}: int = 1;", "", QUOTE, '"{w}"'),
    ("global {w}: int {{ default 0; current 0; initialized false; }}", "", QUOTE, '"{w}"'),
    ("const {w}: int = 1;", "", QUOTE, '"{w}"'),
    ('const "{w}": int = 1; global x: int = {w};', "", READ, 'const("{w}")'),
)


def _module(items: str, body: str = "") -> str:
    return f'module "M" {{ {items} trigger "T" {{ on CARD_ADDED; {body} }} }}'


def _diagnostics(source: str) -> tuple[Diagnostic, ...]:
    _, result = parse_and_validate_source(source)
    return result.diagnostics


def _apply(source: str, fix: SourceFix) -> str:
    span = fix.span
    assert span.start_line == span.end_line == 1 and span.end_column is not None
    return source[: span.start_column - 1] + fix.replacement + source[span.end_column :]


@pytest.mark.parametrize("word", ("import", "If"))
@pytest.mark.parametrize(("items", "body", "help", "replacement"), POSITIONS)
def test_bare_reserved_names_fail_with_a_fix_that_compiles(word, items, body, help, replacement):
    source = _module(items.format(w=word), body.format(w=word))

    (diagnostic,) = _diagnostics(source)
    assert diagnostic.code == "SYNTAX_ERROR"
    assert diagnostic.message == f"{word!r} is a reserved word"
    assert diagnostic.help == help.format(w=word)
    (fix,) = diagnostic.fixes
    assert fix.replacement == replacement.format(w=word)
    assert _diagnostics(_apply(source, fix)) == ()


def test_top_level_constants_reject_bare_reserved_names():
    (diagnostic,) = _diagnostics("const Else: int = 1;\n" + _module(""))
    assert (diagnostic.code, diagnostic.message) == ("SYNTAX_ERROR", "'Else' is a reserved word")


def test_names_that_only_contain_reserved_words_are_ordinary():
    source = _module(
        "global true_flag: int = 0; const breakpoint: int = 1;",
        "let iffy: int = breakpoint; true_flag = iffy; for true_flag from 1 to 2 { }",
    )
    assert _diagnostics(source) == ()


@pytest.mark.parametrize(
    ("source", "code"),
    (
        ("macro import { }", "MACRO_NAME"),
        ("macro m { param If int; }", "MACRO_PARAMETER_NAME"),
        ('trigger "T" { slot import int; on CARD_ADDED; }', "TEMPLATE_SLOT_NAME"),
    ),
)
def test_macro_formal_and_slot_names_keep_their_binder_codes(source, code):
    _, result = parse_and_validate_source(source, source_kind="library")
    assert [item.code for item in result.diagnostics] == [code]
