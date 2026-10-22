"""Full source spans remain attached to shared diagnostics."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import validate_source
from aa2modulus.context.limits import SourceLimitError, SourceLimits
from aa2modulus.core.locations import SourceSpan
from tests.support.source import parse_module


def test_expansion_limit_retains_invocation_and_definition_ranges():
    source = 'macro "log" { WriteLog("x"); }\nmodule "M" { trigger "T" { log(); } }'
    result = validate_source(
        source,
        filename="expansion.aa2m",
        source_limits=SourceLimits(max_expansion_nodes=2),
    )
    (diagnostic,) = result.errors

    assert diagnostic.code == "MACRO_EXPANSION_LIMIT"
    assert diagnostic.source_span == SourceSpan("expansion.aa2m", 2, 28, 2, 33)


def test_parse_tree_limit_retains_the_full_multiline_range():
    source = 'module "M" {\r\n  trigger "T" {}\r\n}'
    with pytest.raises(SourceLimitError) as raised:
        parse_module(source, filename="tree.aa2m", source_limits=SourceLimits(max_nodes=0))

    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "SOURCE_NODE_LIMIT"
    assert diagnostic.source_span == SourceSpan("tree.aa2m", 1, 1, 3, 1)
