"""The lexicon classifies every grammar literal, and the reserved words are exactly its words."""

from __future__ import annotations

import dataclasses
import re

import pytest
from lark.lexer import PatternRE, PatternStr, TerminalDef

from aa2modulus.app.compile import compile_source
from aa2modulus.app.decompile import decompile_module
from aa2modulus.app.editor_lexicon import editor_lexicon
from aa2modulus.context.operation import SourceContext
from aa2modulus.core.source_names import SOURCE_RESERVED
from aa2modulus.syntax.lexicon import Lexicon, build_lexicon, source_lexicon, terminal_literals
from aa2modulus.syntax.parser.engine import shared_parser

_EXPECTED_GROUPS = {
    "keywords": [
        "Else",
        "ElseIf",
        "break",
        "const",
        "continue",
        "current",
        "default",
        "depends_on",
        "description",
        "else",
        "for",
        "from",
        "global",
        "if",
        "import",
        "import.trigger",
        "initialized",
        "let",
        "loop",
        "macro",
        "module",
        "on",
        "param",
        "slot",
        "to",
        "trigger",
        "variable",
    ],
    "types": ["bool", "card", "float", "int", "invalid", "string", "type"],
    "conversions": ["Card"],
    "rawForms": ["raw_action", "raw_event", "raw_expression"],
    "rawPayload": ["constant", "named_constant", "parameters"],
    "literals": ["false", "float_bits", "true"],
    "attributes": ["@allow"],
    "operators": ["!", "!=", "&&", "*", "+", "-", "/", "<", "<=", "==", ">", ">=", "||"],
    "punctuation": ["(", ")", ",", ".", ":", ";", "=", "[", "]", "{", "}"],
}


def _build(terminals: list[TerminalDef]) -> Lexicon:
    return build_lexicon(terminals, ignored=shared_parser().parser.lexer_conf.ignore)


def _grammar_terminals() -> list[TerminalDef]:
    return list(shared_parser().terminals)


def test_groups_patterns_and_comments_match_the_grammar():
    data = source_lexicon().data()
    assert {name: data[name] for name in _EXPECTED_GROUPS} == _EXPECTED_GROUPS
    assert set(data["patterns"]) == {
        "identifier",
        "qualifiedName",
        "integer",
        "float",
        "hexInteger",
    }
    assert data["patterns"]["identifier"] == "[A-Za-z_][A-Za-z0-9_]*"
    assert data["strings"] == "json"
    assert data["comments"] == {"line": "//", "block": ["/*", "*/"]}


def test_reserved_words_are_the_grammar_words_in_any_case():
    words = {
        part.casefold()
        for terminal in shared_parser().terminals
        for literal in terminal_literals(terminal)
        if all(part.isidentifier() for part in literal.split("."))
        for part in literal.split(".")
    }
    assert words == SOURCE_RESERVED


@pytest.mark.parametrize("name", ["var", "event", "compile", "validate"])
def test_former_reserved_words_are_ordinary_names(name):
    source = (
        f'module "M" {{ trigger "T" {{ on CARD_ADDED; let {name}: int = 1; '
        f'{name} = {name} + 1; ClassStorage.SetInt("k", {name}); }} }}'
    )
    binary = compile_source(source)
    decompiled = decompile_module(binary, reject_trailing=True).source
    assert f"let {name}: int" in decompiled
    assert compile_source(decompiled) == binary


@pytest.mark.parametrize(
    ("terminal", "message"),
    [
        (TerminalDef("WHILE", PatternStr("while")), "unclassified grammar literals"),
        (TerminalDef("NUMBER", PatternRE("[0-9]+n")), "unclassified grammar terminal"),
    ],
)
def test_unclassified_grammar_terminal_fails(terminal, message):
    with pytest.raises(ValueError, match=message):
        _build([*_grammar_terminals(), terminal])


def test_vanished_grammar_word_fails():
    terminals = [terminal for terminal in _grammar_terminals() if terminal.name != "LET"]
    with pytest.raises(ValueError, match=r"classified literals missing from the grammar \['let'\]"):
        _build(terminals)


def test_fingerprint_ignores_the_language_version():
    context = SourceContext.create()
    policy = dataclasses.replace(
        context.source_policy, language_version=context.source_policy.language_version + 1
    )
    changed = editor_lexicon(context=SourceContext(context.metadata, policy))
    current = editor_lexicon(context=context)
    assert changed["languageVersion"] != current["languageVersion"]
    assert changed["fingerprint"] == current["fingerprint"]
    assert re.fullmatch(r"[0-9a-f]{64}", current["fingerprint"])


def test_fingerprint_changes_when_a_group_changes():
    lexicon = source_lexicon()
    groups = tuple(
        (name, (*literals, "while") if name == "keywords" else literals)
        for name, literals in lexicon.groups
    )
    assert dataclasses.replace(lexicon, groups=groups).fingerprint != lexicon.fingerprint
