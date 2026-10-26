"""The lexical scan categorizes every lexicon literal without a parse and follows the lexicon."""

from __future__ import annotations

import dataclasses

import pytest

from aa2modulus.syntax.lexicon import source_lexicon
from aa2modulus.syntax.scanner import LexicalScanner, scan_lexical

_CATEGORIES = {
    "keywords": "keyword",
    "types": "type",
    "conversions": "type",
    "rawForms": "keyword",
    "rawPayload": "keyword",
    "literals": "keyword",
    "attributes": "attribute",
    "operators": "operator",
}


def _scan(source: str) -> list[tuple[str, str]]:
    return [(source[token.start : token.end], token.category) for token in scan_lexical(source)]


@pytest.mark.parametrize(
    ("group", "literal"),
    [
        (group, literal)
        for group, literals in source_lexicon().groups
        for literal in literals
        if group != "punctuation"
    ],
)
def test_every_lexicon_literal_gets_its_group_category(group, literal):
    assert _scan(f"x {literal} y") == [(literal, _CATEGORIES[group])]


def test_assignment_is_the_only_colored_punctuation():
    assert _scan("( ) , . : ; = [ ] { }") == [("=", "operator")]


def test_a_module_gets_every_lexical_row():
    source = """import "lib.aa2mi"; // line
@allow(NATIVE_A, NATIVE_B)
module "M" {
  global g: int { default invalid; current 0x1F; initialized false; }
  import.trigger "T" "U" { slot who = -2; }
  trigger "T" {
    on CARD_ADDED;
    let f: float = float_bits(0x7fa00001) * 1.5e3f;
    if !true || f >= .5 { raw_action 7(raw_expression type 3 9 { constant invalid; }); }
  }
}
"""
    assert _scan(source) == [
        ("import", "keyword"),
        ('"lib.aa2mi"', "string"),
        ("// line", "comment"),
        ("@allow", "attribute"),
        ("NATIVE_A", "attributeCode"),
        ("NATIVE_B", "attributeCode"),
        ("module", "keyword"),
        ('"M"', "string"),
        ("global", "keyword"),
        ("int", "type"),
        ("default", "keyword"),
        ("invalid", "keyword"),
        ("current", "keyword"),
        ("0x1F", "number"),
        ("initialized", "keyword"),
        ("false", "keyword"),
        ("import.trigger", "keyword"),
        ('"T"', "string"),
        ('"U"', "string"),
        ("slot", "keyword"),
        ("=", "operator"),
        ("-", "operator"),
        ("2", "number"),
        ("trigger", "keyword"),
        ('"T"', "string"),
        ("on", "keyword"),
        ("let", "keyword"),
        ("float", "type"),
        ("=", "operator"),
        ("float_bits", "keyword"),
        ("0x7fa00001", "number"),
        ("*", "operator"),
        ("1.5e3f", "number"),
        ("if", "keyword"),
        ("!", "operator"),
        ("true", "keyword"),
        ("||", "operator"),
        (">=", "operator"),
        (".5", "number"),
        ("raw_action", "keyword"),
        ("7", "number"),
        ("raw_expression", "keyword"),
        ("type", "type"),
        ("3", "number"),
        ("9", "number"),
        ("constant", "keyword"),
        ("invalid", "keyword"),
    ]


@pytest.mark.parametrize(
    ("source", "category"),
    [
        ("let x: invalid = y;", "type"),
        ("default invalid;", "keyword"),
        ("current /* c */ invalid;", "keyword"),
        ("constant invalid;", "keyword"),
        ("named_constant invalid 3;", "type"),
    ],
)
def test_invalid_is_a_value_only_after_a_value_word(source, category):
    assert ("invalid", category) in _scan(source)


@pytest.mark.parametrize(
    "source",
    ["true_flag", "breakpoint", "IF", "Globals.CurrentDay", "x.type", "import.trigger.x", "f().if"],
)
def test_names_other_than_exact_lexicon_words_get_no_token(source):
    assert _scan(source) == []


def test_allow_codes_end_at_the_closing_parenthesis():
    assert _scan("@allow ( A , /* c */ B ) C @allow(if)") == [
        ("@allow", "attribute"),
        ("A", "attributeCode"),
        ("/* c */", "comment"),
        ("B", "attributeCode"),
        ("@allow", "attribute"),
        ("if", "keyword"),
    ]


def test_tokens_continue_around_and_after_syntax_errors():
    source = 'module "M" { trigger $ "T" {\n let s: string = "open\n if x == 1 /* to the end\n int'
    assert _scan(source) == [
        ("module", "keyword"),
        ('"M"', "string"),
        ("trigger", "keyword"),
        ('"T"', "string"),
        ("let", "keyword"),
        ("string", "type"),
        ("=", "operator"),
        ('"open', "string"),
        ("if", "keyword"),
        ("==", "operator"),
        ("1", "number"),
        ("/* to the end", "comment"),
        (" int", "comment"),
    ]


def test_comment_markers_inside_strings_are_text():
    assert _scan('"a // b /* c" int') == [('"a // b /* c"', "string"), ("int", "type")]


def test_strings_keep_escapes_and_end_at_a_line_break():
    assert _scan('"a \\" b" "c\\\r\nint') == [
        ('"a \\" b"', "string"),
        ('"c\\', "string"),
        ("int", "type"),
    ]


def test_comments_split_at_every_protocol_line_break():
    block = _scan("/* one\r\ntwo\n\nthree */")
    assert block == [("/* one", "comment"), ("two", "comment"), ("three */", "comment")]
    # A line comment runs to ``\n`` only, but a lone ``\r`` still breaks the line.
    assert _scan("// a\rb\nint") == [("// a", "comment"), ("b", "comment"), ("int", "type")]


def test_a_changed_lexicon_group_fails():
    lexicon = source_lexicon()
    added = dataclasses.replace(lexicon, groups=(*lexicon.groups, ("modifiers", ("static",))))
    with pytest.raises(ValueError, match="lexicon groups"):
        LexicalScanner(added)
    removed = dataclasses.replace(lexicon, groups=lexicon.groups[1:])
    with pytest.raises(ValueError, match="lexicon groups"):
        LexicalScanner(removed)


@pytest.mark.parametrize("name", ["identifier", "qualifiedName", "integer", "float", "hexInteger"])
def test_a_changed_literal_pattern_fails(name):
    lexicon = source_lexicon()
    patterns = tuple(
        (key, f"{pattern}_?" if key == name else pattern) for key, pattern in lexicon.patterns
    )
    with pytest.raises(ValueError, match=f"lexicon pattern {name!r}"):
        LexicalScanner(dataclasses.replace(lexicon, patterns=patterns))
