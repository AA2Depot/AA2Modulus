"""Grammar contexts, nested signatures, and authored completion behavior."""

from __future__ import annotations

import pytest

from aa2modulus.context.limits import SourceLimits
from aa2modulus.context.operation import SourceContext
from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.signature.help import signature_help
from aa2modulus.pipeline.analysis import analyze_source

_IMPORTED_LIBRARY = """\
macro "say" {
  param "greeting" string;
  param "suffix" string;
  WriteLog(greeting);
}

trigger "Welcome" {
  slot "greeting" string;
  on CARD_ADDED;
  WriteLog(greeting);
}
"""

_IMPORTED_MODULE = """\
import "library.aa2mi";

module "Frozen Check" {
  global greeting: string = "hello";
  import.trigger "Welcome" "Imported Welcome" { slot "greeting" = greeting; }
  trigger "Start" {
    say(greeting, "!");
    WriteLog(greeting);
  }
}
"""


def test_keywords_follow_the_grammar_state(context):
    assert [item.label for item in completions("mod", 3, context)] == ["module"]

    condition = 'module "M" { trigger "T" { if '
    assert {"true", "false"} <= {
        item.label for item in completions(condition, len(condition), context)
    }

    body = 'module "M" { trigger "T" { loop { '
    assert {"break", "continue", "Else", "ElseIf"} <= {
        item.label for item in completions(body, len(body), context)
    }


@pytest.mark.parametrize("comment", ["/* done */", "// done\n"])
def test_completion_resumes_after_a_closed_comment(context, comment):
    source = 'module "M" { ' + comment
    assert "trigger" in {item.label for item in completions(source, len(source), context)}


def test_nested_calls_keep_outer_signature_and_active_argument(context):
    source = 'module "M" { trigger "T" { let n: int = Subtract(1, Subtract(2, 3), '
    result = signature_help(source, len(source), context)
    assert result is not None
    assert [item.label for item in result.signatures] == ["Subtract(left: int, right: int)"]
    assert result.active_parameter == 2

    parenthesized = 'module "M" { trigger "T" { let n: int = Subtract(1, (2'
    result = signature_help(parenthesized, len(parenthesized), context)
    assert result is not None
    assert result.signatures[0].label == "Subtract(left: int, right: int)"
    assert result.active_parameter == 1


def test_authored_macro_signature_uses_current_partial_source(context):
    source = 'macro LocalMacro { param amount int; } module "M" { trigger "T" { LocalMacro(1); } }'
    cursor = source.index("LocalMacro(") + len("LocalMacro(")
    analysis = analyze_source(source, context=context)

    current = signature_help(source, cursor, context, analysis=analysis)
    stale = signature_help(source[:cursor], cursor, context, analysis=analysis)
    assert current is not None
    assert current.signatures[0].label == "LocalMacro(amount: int)"
    assert stale is None

    invalid = source + " @"
    result = signature_help(
        invalid, cursor, context, analysis=analyze_source(invalid, context=context)
    )
    assert result is not None
    assert result.signatures[0].label == "LocalMacro(amount: int)"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('module "M" { trigger "T" { StopT', "StopThread"),
        (
            'module "M" { trigger "T" { let target: int = Context.NpcAnswer',
            "Context.NpcAnswerTarget",
        ),
        (
            'module "M" { trigger "T" { let affection: int = Constants.Relationship.LO',
            "Constants.Relationship.LOVE",
        ),
    ],
)
def test_completion_keeps_canonical_names(context, source, expected):
    assert expected in {item.label for item in completions(source, len(source), context)}


def test_user_macro_can_use_a_name_that_was_only_a_gui_alias(context):
    source = 'macro PSetStaminaP {} module "M" { trigger "T" { PSetStaminaP(); } }'
    analysis = analyze_source(source, context=context)
    cursor = source.index("PSetStaminaP();") + len("PSetStaminaP")
    items = completions(source, cursor, context, analysis=analysis)

    matching = [item for item in items if item.label == "PSetStaminaP"]
    assert analysis.result.is_valid
    assert len(matching) == 1
    assert matching[0].kind.name == "Function"


def test_imported_macro_signature_and_template_scope_remain_available(tmp_path):
    (tmp_path / "library.aa2mi").write_text(_IMPORTED_LIBRARY, encoding="utf-8")
    context = SourceContext.create(filename=str(tmp_path / "module.aa2m"), import_base=tmp_path)
    analysis = analyze_source(_IMPORTED_MODULE, context=context)
    assert analysis.result.is_valid

    call_cursor = _IMPORTED_MODULE.index("say(") + len("say(greeting, ")
    result = signature_help(_IMPORTED_MODULE, call_cursor, context, analysis=analysis)
    assert result is not None
    assert result.active_parameter == 1
    assert any(item.label == "say(greeting: string, suffix: string)" for item in result.signatures)

    completion_cursor = _IMPORTED_MODULE.rindex("WriteLog(greeting)")
    items = completions(_IMPORTED_MODULE, completion_cursor, context, analysis=analysis)
    assert any(item.label == "WriteLog" for item in items)


def test_unknown_qualified_prefix_does_not_become_a_grammar_terminal(tmp_path):
    (tmp_path / "library.aa2mi").write_text(_IMPORTED_LIBRARY, encoding="utf-8")
    context = SourceContext.create(filename=str(tmp_path / "module.aa2m"), import_base=tmp_path)
    source = _IMPORTED_MODULE.replace("import.trigger", "unknown.qualified")
    cursor = source.index("say(") + len("say(")
    # The unknown line is one dropped fault, as if it were not there.
    line = '  unknown.qualified "Welcome" "Imported Welcome" { slot "greeting" = greeting; }\n'
    dropped = source.replace(line, "")
    dropped_cursor = dropped.index("say(") + len("say(")

    assert [item.label for item in completions(source, cursor, context)] == [
        item.label for item in completions(dropped, dropped_cursor, context)
    ]
    assert signature_help(source, cursor, context) == signature_help(
        dropped, dropped_cursor, context
    )


def test_authored_completions_respect_macro_and_template_scopes(context):
    macro_source = (
        'macro Work { param Formal int; if Formal > 0 {} } module "M" '
        '{ global Shared: int = 0; trigger "T" { let Local: int = 0; } }'
    )
    analysis = analyze_source(macro_source, context=context)
    cursor = macro_source.index("Formal >")
    names = {item.label for item in completions(macro_source, cursor, context, analysis=analysis)}
    assert "Formal" in names
    assert "Shared" not in names
    assert "Local" not in names

    template_source = (
        'macro Work { param Formal int; } trigger "Template" '
        "{ slot ArgSlot int; if ArgSlot > 0 {} }"
    )
    analysis = analyze_source(template_source, context=context, source_kind="library")
    cursor = template_source.index("ArgSlot >")
    names = {
        item.label for item in completions(template_source, cursor, context, analysis=analysis)
    }
    assert "ArgSlot" in names
    assert "Formal" not in names


def test_authored_completion_preserves_case_distinct_names(context):
    source = (
        'module "M" { global X: int = 0; global x: int = 1; '
        'trigger "T" { let value: int = 0; let result: int = '
    )
    complete = source + "X; } }"
    cursor = source.index("= ", source.index("let result")) + 2
    names = {
        item.label
        for item in completions(
            complete, cursor, context, analysis=analyze_source(complete, context=context)
        )
    }
    assert {"X", "x"} <= names


def test_block_strings_get_no_completion_until_closed(context):
    inside = 'module "M" {\n  description """\n    tri'
    assert completions(inside, len(inside), context) == []
    after = inside + '\n    """;\n  tri'
    assert [item.label for item in completions(after, len(after), context)] == ["trigger"]


def test_incomplete_prefixes_and_resource_limits_return_no_items(context):
    assert completions('module "M" { trigger "T" { @', 30, context) == []

    limited = SourceContext.create(source_limits=SourceLimits(max_source_chars=3))
    assert completions("module", 3, limited) == []
    assert signature_help("module", 3, limited) is None

    nodes = SourceContext.create(source_limits=SourceLimits(max_nodes=0))
    assert completions("module", 3, nodes) == []
    assert signature_help("module", 3, nodes) is None

    nesting = SourceContext.create(source_limits=SourceLimits(max_nesting_depth=1))
    source = 'module "M" { trigger "T" { let x: int = Outer((1'
    assert completions(source, len(source), nesting) == []
