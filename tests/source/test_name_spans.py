"""Exact name-token locations carried through source parsing."""

from __future__ import annotations

import pytest

from aa2modulus.core.locations import SourceSpan
from aa2modulus.syntax.ast import (
    SourceAction,
    SourceAssignment,
    SourceFor,
    SourceModule,
    SourceName,
    SourceRawExpression,
    SourceRawVariable,
)
from aa2modulus.syntax.parser.errors import SourceParseError
from aa2modulus.syntax.parser.units import parse_library_source, parse_source_ast, parse_source_unit


def _token_span(filename: str, line_no: int, line: str, token: str) -> SourceSpan:
    start = line.index(token) + 1
    return SourceSpan(filename, line_no, start, line_no, start + len(token) - 1)


def test_declaration_and_use_name_spans_are_token_exact_and_equality_neutral():
    filename = "names.aa2m"
    lines = [
        'module "M\\u0020😀" {',
        '  global "global name": int = 0;',
        '  trigger "T\\"1" {',
        "    on Foo.Bar;",
        '    let "local\\u0020name": int = variable("global name");',
        '    variable("local name") = Foo.Bar(ThisCard);',
        "    for index from 0 to 1 { SetVariable(index); }",
        '    raw_action 9002(raw_expression int 2 { variable "raw\\u0020name"; });',
        "  }",
        "}",
    ]
    source = "\r\n".join(lines)
    module = parse_source_ast(source, filename=filename)
    trigger = module.triggers[0]

    assert module.name == "M 😀"
    assert module.name_span == _token_span(filename, 1, lines[0], '"M\\u0020😀"')
    assert module.globals[0].name_span == _token_span(filename, 2, lines[1], '"global name"')
    assert trigger.name_span == _token_span(filename, 3, lines[2], '"T\\"1"')
    assert trigger.events[0].name_span == _token_span(filename, 4, lines[3], "Foo.Bar")
    assert trigger.locals[0].name_span == _token_span(filename, 5, lines[4], '"local\\u0020name"')
    assert trigger.locals[0].default.name_span == _token_span(
        filename, 5, lines[4], '"global name"'
    )

    assignment, loop, raw_action = trigger.statements
    assert isinstance(assignment, SourceAssignment)
    assert assignment.target_span == _token_span(filename, 6, lines[5], '"local name"')
    assert assignment.value.name_span == _token_span(filename, 6, lines[5], "Foo.Bar")
    assert assignment.value.arguments[0].name_span == _token_span(filename, 6, lines[5], "ThisCard")
    assert isinstance(loop, SourceFor)
    assert loop.target_span == _token_span(filename, 7, lines[6], "index")
    assert loop.body[0].name_span == _token_span(filename, 7, lines[6], "SetVariable")
    raw_expression = raw_action.arguments[0]
    assert isinstance(raw_expression, SourceRawExpression)
    assert isinstance(raw_expression.payload, SourceRawVariable)
    assert raw_expression.payload.name_span == _token_span(
        filename, 8, lines[7], '"raw\\u0020name"'
    )

    assert module == SourceModule(
        "M 😀",
        globals=module.globals,
        triggers=(type(trigger)(trigger.name, trigger.events, trigger.locals, trigger.statements),),
    )
    assert SourceName("value") == SourceName("value", name_span=module.name_span)
    assert SourceAction(name="A", name_span=module.name_span) == SourceAction(name="A")


def test_library_definition_import_and_slot_names_have_individual_spans():
    filename = "library.aa2mi"
    library_lines = [
        'import "sub\\u002elib.aa2mi";',
        "macro Sum {",
        "  param left int;",
        "  Add(left, 1);",
        "}",
        'trigger "Template" {',
        "  slot amount int;",
        "  on Foo.Bar;",
        "}",
    ]
    library = parse_library_source("\n".join(library_lines), filename=filename)
    (import_,) = library.imports
    (macro,) = library.macros
    (template,) = library.templates

    assert import_.path_span == _token_span(filename, 1, library_lines[0], '"sub\\u002elib.aa2mi"')
    assert macro.name_span == _token_span(filename, 2, library_lines[1], "Sum")
    assert macro.parameters[0].name_span == _token_span(filename, 3, library_lines[2], "left")
    assert macro.body[0].name_span == _token_span(filename, 4, library_lines[3], "Add")
    assert template.trigger.name_span == _token_span(filename, 6, library_lines[5], '"Template"')
    assert template.slots[0].name_span == _token_span(filename, 7, library_lines[6], "amount")
    assert template.trigger.events[0].name_span == _token_span(
        filename, 8, library_lines[7], "Foo.Bar"
    )

    module_lines = [
        'module "M" {',
        '  import.trigger "Template" "Renamed" {',
        "    slot amount = 1;",
        "  }",
        "}",
    ]
    unit = parse_source_unit("\n".join(module_lines), filename="imports.aa2m")
    imported = unit.module.triggers[0]
    assert imported.template_span == _token_span("imports.aa2m", 2, module_lines[1], '"Template"')
    assert imported.name_span == _token_span("imports.aa2m", 2, module_lines[1], '"Renamed"')
    assert imported.slots[0].name_span == _token_span("imports.aa2m", 3, module_lines[2], "amount")


def test_source_names_in_errors_keep_token_or_eof_point_without_changing_rendering():
    filename = "broken.aa2m"
    with_error = 'module "M" { trigger "T" { SetVariable(,); } }'
    try:
        parse_source_ast(with_error, filename=filename)
    except SourceParseError as error:
        assert error.source_span == _token_span(filename, 1, with_error, ",")
        assert str(error).startswith("broken.aa2m:1:")
    else:
        raise AssertionError("invalid expression unexpectedly parsed")

    eof = 'module "M" {'
    try:
        parse_source_ast(eof, filename=filename)
    except SourceParseError as error:
        assert error.source_span == SourceSpan(filename, 1, len(eof) + 1, 1, len(eof) + 1)
        assert str(error) == f"{filename}:1:{len(eof) + 1}: error[SYNTAX_ERROR]: {error.message}"
    else:
        raise AssertionError("incomplete module unexpectedly parsed")


def test_names_after_unicode_and_comments_keep_tokens_separate_from_multiline_nodes():
    source = (
        'module "😀" { /* global "decoy" */ global "real": int = 0;\r\n'
        'trigger "T" {\r\n'
        '  Notification /* Notification("decoy") */ (\r\n'
        '    "x"\r\n'
        "  );\r\n"
        "} }"
    )
    module = parse_source_ast(source, filename="comments.aa2m")
    assert module.globals[0].name_span == SourceSpan("comments.aa2m", 1, 42, 1, 47)
    action = module.triggers[0].statements[0]
    assert action.name_span == SourceSpan("comments.aa2m", 3, 3, 3, 14)
    assert action.source_span == SourceSpan("comments.aa2m", 3, 3, 5, 4)


@pytest.mark.parametrize(
    ("source", "kind", "code", "span"),
    [
        ("macro emit {}", "module", "MODULE_REQUIRED", SourceSpan("kind", 1, 1, 1, 13)),
        ('module "M" {}', "library", "LIBRARY_MODULE", SourceSpan("kind", 1, 1, 1, 13)),
    ],
)
def test_source_kind_errors_retain_the_existing_declaration_range(source, kind, code, span):
    with pytest.raises(SourceParseError) as raised:
        parse_source_unit(source, kind=kind, filename="kind")
    assert raised.value.code == code
    assert raised.value.source_span == span
