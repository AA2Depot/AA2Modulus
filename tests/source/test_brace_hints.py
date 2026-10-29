"""A syntax error caused by an unbalanced brace names the brace pair at fault."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source

EXTRA_CLOSE = """\
module "m" {
  trigger "a" {
    on CARD_ADDED;
    if true {
      }
    }
  }
  trigger "b" {
    on CARD_ADDED;
  }
}
"""

MISSING_CLOSE = """\
module "m" {
  trigger "a" {
    on CARD_ADDED;
    WriteLog("a");
  trigger "b" {
    on CARD_ADDED;
  }
}
"""

MODULE_CLOSED_EARLY = """\
module "m" {
  trigger "a" {
    on CARD_ADDED;
    if true {
      }
    }
  }
  trigger "b" {
    on CARD_ADDED;
  }
"""


def _errors(source: str):
    return [
        (
            item.line,
            item.code,
            item.help,
            item.notes,
            [str(note.span.start_line) + ":" + note.message for note in item.related],
        )
        for item in validate_source(source, filename="x.aa2m").diagnostics
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            EXTRA_CLOSE,
            (
                11,
                "SYNTAX_ERROR",
                "the `{` on line 4 and the `}` on line 5 are indented differently; "
                "a `}` is probably missing or extra between them",
                (),
                ["4:this `{` is closed on line 5", "5:this `}` closes the `{` on line 4"],
            ),
        ),
        (
            MISSING_CLOSE,
            (
                5,
                "SYNTAX_ERROR",
                "the `{` on line 2 and the `}` on line 8 are indented differently; "
                "a `}` is probably missing or extra between them",
                (),
                ["2:this `{` is closed on line 8", "8:this `}` closes the `{` on line 2"],
            ),
        ),
        (
            MODULE_CLOSED_EARLY,
            (
                8,
                "TEMPLATE_LIBRARY_ONLY",
                "the `{` on line 4 and the `}` on line 5 are indented differently; "
                "a `}` is probably missing or extra between them",
                (),
                ["4:this `{` is closed on line 5", "5:this `}` closes the `{` on line 4"],
            ),
        ),
    ],
)
def test_brace_fault_names_the_first_misindented_pair(source, expected):
    assert _errors(source) == [expected]


def test_unclosed_brace_without_a_misindented_pair_is_named():
    source = 'module "m" {\n  trigger "a" {\n    on CARD_ADDED;\n  }\n'

    assert _errors(source) == [
        (
            5,
            "SYNTAX_ERROR",
            "the `{` on line 1 is never closed",
            (),
            ["1:this `{` is never closed"],
        )
    ]


@pytest.mark.parametrize(
    "statement",
    ["x = ;", 'WriteLog("}"); // {\n    x = ;'],
)
def test_balanced_braces_add_no_hint(statement):
    source = f'module "m" {{\n  trigger "a" {{\n    on CARD_ADDED;\n    {statement}\n  }}\n}}\n'

    assert [(code, help, related) for _, code, help, _, related in _errors(source)] == [
        ("SYNTAX_ERROR", None, [])
    ]


def test_an_existing_help_line_is_kept_and_the_hint_becomes_a_note():
    source = 'module "m" {\n  trigger "a" {\n    on CARD_ADDED;\n    x += 1;\n}\n'

    [(line, code, help, notes, related)] = _errors(source)

    assert (line, code) == (4, "SYNTAX_ERROR")
    assert help == "aa2m has no `+=`; write `x = x + ...;`"
    assert notes == (
        "the `{` on line 2 and the `}` on line 5 are indented differently; "
        "a `}` is probably missing or extra between them",
    )
    assert related == ["2:this `{` is closed on line 5", "5:this `}` closes the `{` on line 2"]
