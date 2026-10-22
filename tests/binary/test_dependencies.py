"""Dependency strings keep their authored order and name-only semantics."""

from __future__ import annotations

import struct

import pytest

from aa2modulus.app.compile import CompileError, compile_module, validate_source
from aa2modulus.binary.reader import decode_module
from aa2modulus.binary.writer import encode_module
from aa2modulus.model.records import Module
from aa2modulus.validation.validator.module import validate_module


def _string(value: str) -> bytes:
    raw = value.encode("utf-16-le")
    return struct.pack("<I", len(raw) // 2) + raw


def _wire(dependencies: tuple[str, ...]) -> bytes:
    return (
        _string("D")
        + _string("")
        + struct.pack("<II", 0, 0)
        + struct.pack("<I", len(dependencies))
        + b"".join(_string(item) for item in dependencies)
    )


def test_dependency_diagnostics_change_profile_severity_without_changing_native_bytes():
    module = decode_module(_wire(("Z", "A", "", "  ", "D", "A")), reject_trailing=True).module
    strict = validate_module(module)
    native = validate_module(module, profile="native")
    expected = [
        (
            "INVALID_MODULE_DEPENDENCY",
            "module dependency cannot be empty",
            ("module", "dependencies", 2),
        ),
        (
            "INVALID_MODULE_DEPENDENCY",
            "module dependency cannot be empty",
            ("module", "dependencies", 3),
        ),
        (
            "INVALID_MODULE_DEPENDENCY",
            "module cannot depend on itself: 'D'",
            ("module", "dependencies", 4),
        ),
        (
            "DUPLICATE_MODULE_DEPENDENCY",
            "module dependency 'A' is listed more than once",
            ("module", "dependencies", 5),
        ),
    ]
    strict_items = [item for item in strict.diagnostics if item.code.endswith("MODULE_DEPENDENCY")]
    native_items = [item for item in native.diagnostics if item.code.endswith("MODULE_DEPENDENCY")]
    expected_shape = [(item.code, item.message, item.path) for item in strict_items]
    assert expected_shape == expected
    assert [(item.code, item.message, item.path) for item in native_items] == expected
    assert all(item.severity == "error" for item in strict_items)
    assert all(item.severity == "warning" for item in native_items)
    assert strict.errors == tuple(strict_items)
    expected_wire = _wire(("Z", "A", "", "  ", "D", "A"))
    assert encode_module(module) == expected_wire
    assert compile_module(module, profile="native") == expected_wire
    with pytest.raises(CompileError) as raised:
        compile_module(module)
    assert [item.code for item in raised.value.diagnostics] == [item[0] for item in expected]


def test_dependency_names_do_not_supply_imported_globals():
    source = """module "Receiver" {
      depends_on "Provider";
      trigger "Init" { let copy: int = variable("external"); }
    }"""
    result = validate_source(source)
    assert {item.code for item in result.errors} == {"UNDEFINED_VARIABLE"}
    assert {item.help for item in result.errors} == {
        "declare it in this module: `global external: int = 0;`"
    }


def test_empty_dependency_vector_is_exact_native_wire():
    assert encode_module(Module("D")) == _wire(())
