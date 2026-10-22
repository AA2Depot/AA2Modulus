"""User-visible source limits and the guards that prevent excessive work."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import CompileError, compile_source, validate_source
from aa2modulus.context.limits import SourceLimitError, SourceLimits
from tests.support.source import parse_module


def _error(source: str, limits: SourceLimits, code: str):
    result = validate_source(source, filename="limits.aa2m", source_limits=limits)
    assert len(result.errors) == 1
    diagnostic = result.errors[0]
    assert diagnostic.code == code
    assert diagnostic.filename == "limits.aa2m"
    return diagnostic


def test_source_character_limit_counts_unicode_codepoints_at_the_boundary():
    source = 'module "é😀" {}'
    assert len(source) == len(source.encode("utf-8")) - 4
    assert validate_source(
        source, source_limits=SourceLimits(max_source_chars=len(source))
    ).is_valid
    diagnostic = _error(source, SourceLimits(max_source_chars=len(source) - 1), "SOURCE_SIZE_LIMIT")
    assert (diagnostic.line, diagnostic.column) == (1, 1)


def test_deep_authored_expressions_fail_with_source_diagnostics():
    cases = (
        (
            'module "M" { trigger "T" { Notification(' + "(" * 1200 + '"x"' + ")" * 1200 + "); } }",
            "SOURCE_DEPTH_LIMIT",
        ),
        (
            'module "M" { trigger "T" { Notification(' + "A(" * 300 + '"x"' + ")" * 300 + "); } }",
            "SOURCE_DEPTH_LIMIT",
        ),
        (
            'module "M" { trigger "T" { Notification(' + "!" * 1200 + "true); } }",
            "SOURCE_DEPTH_LIMIT",
        ),
        (
            'module "M" { trigger "T" { Notification(' + "1 + " * 100 + "1); } }",
            "SOURCE_NESTING_LIMIT",
        ),
        (
            'module "M" { trigger "T" { '
            + "if true { " * 70
            + 'Notification("x"); '
            + "} " * 70
            + "} }",
            "SOURCE_NESTING_LIMIT",
        ),
    )
    for source, code in cases:
        diagnostic = _error(source, SourceLimits(), code)
        assert diagnostic.line >= 1 and diagnostic.column >= 1


def test_strings_and_comments_do_not_consume_syntax_depth():
    source = 'module "M {{{ ((( }}}" { description "(({{}}))"; /* {{{ ((( */ }'
    assert validate_source(source, source_limits=SourceLimits(max_syntax_depth=8)).is_valid


def test_supported_nesting_boundary_compiles_and_next_level_is_rejected():
    limits = SourceLimits(max_syntax_depth=512, max_nesting_depth=128)

    def source(depth: int) -> str:
        return 'module "M" { trigger "T" { ' + "loop {" * depth + "}" * depth + "} }"

    compile_source(source(128), source_limits=limits)
    with pytest.raises(CompileError) as raised:
        compile_source(source(129), source_limits=limits)
    assert raised.value.diagnostics[0].code == "SOURCE_NESTING_LIMIT"


def test_source_character_limit_rejects_before_parser_construction(monkeypatch):
    def unexpected_parser():
        raise AssertionError("oversized text reached the parser")

    monkeypatch.setattr("aa2modulus.syntax.parser.engine.shared_parser", unexpected_parser)
    with pytest.raises(SourceLimitError) as raised:
        parse_module('module "M" {}', source_limits=SourceLimits(max_source_chars=0))
    assert raised.value.diagnostic.code == "SOURCE_SIZE_LIMIT"


def test_syntax_depth_limit_rejects_before_ast_transformation(monkeypatch):
    def unexpected_transformer(filename):
        raise AssertionError("over-budget tree reached AST transformation")

    monkeypatch.setattr("aa2modulus.syntax.parser.units.SourceTransformer", unexpected_transformer)
    with pytest.raises(SourceLimitError) as raised:
        parse_module('module "M" {}', source_limits=SourceLimits(max_syntax_depth=1))
    assert raised.value.diagnostic.code == "SOURCE_DEPTH_LIMIT"


def test_maximum_macro_expansion_budget_is_applied_by_source_validation():
    source = 'macro "log" { WriteLog("x"); } module "M" { trigger "T" { log(); } }'
    assert validate_source(source, source_limits=SourceLimits(max_expansion_nodes=4)).is_valid
    _error(source, SourceLimits(max_expansion_nodes=3), "MACRO_EXPANSION_LIMIT")
