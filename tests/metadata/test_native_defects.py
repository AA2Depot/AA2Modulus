"""Policy-recorded native defects are diagnosed wherever the target appears."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import CompileError, compile_source, validate_source
from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.context.operation import SourceContext
from aa2modulus.metadata.schema import MetadataError
from aa2modulus.validation.validator.module import validate_module
from tests.support.policy import edited_policy, policy_context
from tests.support.source import parse_module

# Native-format evidence N12: STRING/13 declares slot 0 int but reads a string.
SOURCE = 'module "M" { trigger "T" { on CARD_ADDED; Notification(Text.Replace(0, 1, 2, "x")); } }'


def _defects(result):
    return [item for item in result.diagnostics if item.code == "NATIVE_DEFECTIVE_EXPRESSION"]


def test_text_replace_is_a_strict_error_naming_the_source_spelling():
    (defect,) = _defects(validate_source(SOURCE))
    assert defect.severity == "error"
    assert defect.message.startswith("Text.Replace cannot work in AAUnlimited: ")
    assert "Thread::StringReplace reads it as a string" in defect.message
    assert (defect.line, defect.column) == (1, SOURCE.index("Text.Replace") + 1)
    with pytest.raises(CompileError):
        compile_source(SOURCE)


def test_native_profile_warns_and_decoded_binaries_are_diagnosed():
    context = SourceContext.create()
    module = parse_module(SOURCE, context=context)
    checks = {"metadata": context.metadata, "catalog": context.catalog}
    (native,) = _defects(validate_module(module, profile="native", **checks))
    assert native.severity == "warning"
    decoded = decode_module(encode_module(module)).module
    (strict,) = _defects(validate_module(decoded, **checks))
    assert strict.severity == "error"


def test_the_policy_entry_is_the_only_switch(tmp_path):
    context = policy_context(edited_policy(tmp_path, lambda document: document.pop("defects")))
    assert context.source_policy.expression_defects == ()
    assert compile_source(SOURCE, context=context)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"string:13": {"declared": ["string", "int", "int", "string"], "reason": "x"}},
            r"native declaration is now \(int, int, int, string\)",
        ),
        (
            {"string:9999": {"declared": ["int"], "reason": "x"}},
            "unknown expression string:9999",
        ),
        ({"string:13": {"declared": ["text"], "reason": "x"}}, "must be one of invalid"),
        ({"string:13": {"declared": ["int"]}}, "missing required key"),
    ],
)
def test_defect_entries_are_guarded_against_the_registry(tmp_path, entry, message):
    path = edited_policy(tmp_path, lambda document: document["defects"].update(expressions=entry))
    with pytest.raises(MetadataError, match=message):
        policy_context(path)
