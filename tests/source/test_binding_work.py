"""Binding's public work limit rejects pathological authored expressions."""

from __future__ import annotations

from aa2modulus.app.compile import validate_source
from aa2modulus.context.limits import SourceLimits


def test_binding_work_limit_fails_at_the_public_validation_boundary():
    source = 'module "M" { trigger "T" { let value: int = Lua.CallInt("compute") + 1; } }'
    result = validate_source(
        source,
        filename="binding-work.aa2m",
        source_limits=SourceLimits(max_binding_work=5),
    )
    assert [item.code for item in result.errors] == ["SOURCE_BINDING_WORK_LIMIT"]
    diagnostic = result.errors[0]
    assert diagnostic.filename == "binding-work.aa2m"
    # The limit is crossed at the literal operand, the last node bound.
    assert (diagnostic.line, diagnostic.column) == (1, source.rindex("1") + 1)
