"""Keyword snippets follow the grammar and the file's source kind, and expand to valid source."""

from __future__ import annotations

import re
from dataclasses import replace

import pytest
from lsprotocol.types import CompletionItemKind, InsertTextFormat

from aa2modulus.app.compile import validate_source
from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.pipeline.analysis import analyze_source
from aa2modulus.syntax.parser.errors import SourceParseError

_TRIGGER = 'module "M" {\n\ttrigger "T" {\n\t\ton CARD_ADDED;\n\t\t|\n\t}\n}'
_STATEMENTS = {("if", "if block"), ("if", "if and else blocks"), ("loop", "loop block")}
_TRIGGER_ITEMS = {
    *_STATEMENTS,
    ("for", "counted loop with its local"),
    ("let", "trigger local"),
    ("on", "event"),
}
_TOP_LEVEL = {
    ("const", "compile-time constant"),
    ("import", "library import"),
    ("macro", "statement macro with a parameter"),
}

_POSITIONS = [
    ("m.aa2m", "|", {*_TOP_LEVEL, ("module", "module with a trigger")}),
    ("m.aa2m", "const A: int = 1;\n|", {*_TOP_LEVEL, ("module", "module with a trigger")}),
    ("m.aa2m", 'module "M" {}\n|', _TOP_LEVEL),
    (
        "m.aa2m",
        'module "M" {\n\t|\n}',
        {
            ("const", "compile-time constant"),
            ("depends_on", "module dependency"),
            ("description", "module description"),
            ("global", "module global"),
            ("import.trigger", "trigger template instance"),
            ("trigger", "trigger with an event"),
        },
    ),
    ("m.aa2m", 'module "M" {\n\timport.trigger "T" "I" {\n\t\t|\n\t}\n}', {("slot", "slot value")}),
    ("m.aa2m", _TRIGGER, _TRIGGER_ITEMS),
    ("m.aa2m", _TRIGGER.replace("|", "if true {\n|\n}"), {*_STATEMENTS, ("for", "counted loop")}),
    (
        "m.aa2m",
        _TRIGGER.replace("|", "if true {\n}\n|"),
        {*_TRIGGER_ITEMS, ("else", "else block"), ("else if", "else if block")},
    ),
    ("m.aa2m", _TRIGGER.replace("|", "break |"), set()),
    ("m.aa2m", _TRIGGER.replace("|", "let x: int = |;"), set()),
    ("m.aa2m", 'module "M" {\n\tglobal x: int = |;\n}', set()),
    ("m.aa2m", "macro m {\n\t|\n}", {*_STATEMENTS, ("param", "macro parameter")}),
    (
        "l.aa2mi",
        "|",
        {
            *_TOP_LEVEL,
            ("library", "macro and trigger template"),
            ("trigger", "trigger template with a slot"),
        },
    ),
    ("l.aa2mi", "const A: int = 1;\n|", {*_TOP_LEVEL, ("trigger", "trigger template with a slot")}),
    ("l.aa2mi", 'trigger "T" {\n\t|\n}', {*_TRIGGER_ITEMS, ("slot", "template slot")}),
]


def _kind(filename):
    return "library" if filename.endswith(".aa2mi") else "module"


def _snippets(context, filename, text, *, snippet_support=True):
    source = text.replace("|", "")
    operation = replace(context, filename=filename)
    items = completions(source, text.index("|"), operation, snippet_support=snippet_support)
    return source, [item for item in items if item.kind == CompletionItemKind.Snippet]


def _expanded(source, item):
    """The source after inserting ``item`` with every placeholder at its default."""

    body = re.sub(r"\$\{\d+\|([^,|]*)[^}]*\}", r"\1", item.text_edit.new_text)
    body = re.sub(r"\$\{\d+:([^}]*)\}", r"\1", body)
    body = re.sub(r"\$\d+", "", body)
    codec = PositionCodec(source)
    start = codec.offset(item.text_edit.range.start)
    end = codec.offset(item.text_edit.range.end)
    return source[:start] + body + source[end:]


@pytest.mark.parametrize(("filename", "text", "expected"), _POSITIONS)
def test_snippets_follow_the_grammar_and_expand_to_parsable_source(
    context, filename, text, expected
):
    source, items = _snippets(context, filename, text)
    operation = replace(context, filename=filename)

    assert {(item.label, item.detail) for item in items} == expected
    assert all(item.insert_text_format == InsertTextFormat.Snippet for item in items)
    for item in items:
        completed = _expanded(source, item)
        failure = analyze_source(completed, context=operation, source_kind=_kind(filename)).failure
        # A module file that still lacks its module parses but is incomplete.
        assert not isinstance(failure, SourceParseError) or failure.code == "MODULE_REQUIRED", (
            item.label,
            completed,
        )


@pytest.mark.parametrize("filename", ["m.aa2m", "l.aa2mi"])
@pytest.mark.parametrize("text", ["|", "  // notes\n|\n"])
def test_empty_document_starter_ranks_first_and_validates_clean(context, filename, text):
    source, items = _snippets(context, filename, text)
    starter = min(items, key=lambda item: item.sort_text)
    completed = _expanded(source, starter)

    assert starter.label == ("library" if filename.endswith(".aa2mi") else "module")
    assert [item.sort_text for item in items].count("0") == 1
    result = validate_source(
        completed, context=replace(context, filename=filename), source_kind=_kind(filename)
    )
    assert result.diagnostics == ()


def test_starter_is_not_offered_once_the_document_has_content(context):
    _, items = _snippets(context, "l.aa2mi", "|\nconst A: int = 1;")

    assert "0" not in {item.sort_text for item in items}


@pytest.mark.parametrize(
    ("filename", "text", "absent"),
    [
        ("l.aa2mi", "|", "module"),
        ("m.aa2m", "|", "trigger"),
        ("m.aa2m", 'module "M" {}\n|', "module"),
        ("m.aa2m", '|\nmodule "M" {}', "module"),
    ],
)
@pytest.mark.parametrize("snippet_support", [False, True])
def test_source_kind_filters_keywords_and_snippets(
    context, filename, text, absent, snippet_support
):
    source = text.replace("|", "")
    operation = replace(context, filename=filename)
    items = completions(source, text.index("|"), operation, snippet_support=snippet_support)

    assert absent not in {item.label for item in items}


@pytest.mark.parametrize(
    ("filename", "text"),
    [("m.aa2m", "|"), ("m.aa2m", _TRIGGER), ("l.aa2mi", "|")],
    ids=["module-top-level", "trigger-body", "library-top-level"],
)
def test_clients_without_snippet_support_get_no_snippets(context, filename, text):
    _, items = _snippets(context, filename, text, snippet_support=False)

    assert items == []


def test_snippets_follow_the_typed_prefix_and_replace_it(context):
    text = _TRIGGER.replace("|", "lo|")
    source, items = _snippets(context, "m.aa2m", text)

    assert [item.label for item in items] == ["loop"]
    assert _expanded(source, items[0]) == _TRIGGER.replace("|", "loop {\n\t\n}")
