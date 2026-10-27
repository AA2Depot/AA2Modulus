"""Exact source diagnostic contracts across public APIs."""

from __future__ import annotations

import struct
from dataclasses import dataclass

import pytest

from aa2modulus.app.compile import CompileError, compile_source, validate_source
from aa2modulus.semantics.binding.state import SourceBindingError
from aa2modulus.syntax.parser.errors import SourceParseError
from aa2modulus.syntax.parser.units import parse_source_ast
from tests.support.source import parse_module


@dataclass(frozen=True)
class DiagnosticCase:
    name: str
    source: str
    code: str
    token: str
    error_type: type[SourceParseError | SourceBindingError]

    @property
    def line_column(self) -> tuple[int, int]:
        offset = self.source.index(self.token)
        return self.source.count("\n", 0, offset) + 1, offset - self.source.rfind("\n", 0, offset)


RAW_PAYLOAD_CASES = (
    DiagnosticCase(
        "raw-constant-payload",
        'module "M" { trigger "T" { raw_action 9001(raw_expression int 9001 { constant 2; }); } }',
        "PAYLOAD_MISMATCH",
        "raw_expression",
        SourceParseError,
    ),
)

CASES = (
    DiagnosticCase(
        "invalid-module-name-escape",
        'module "Bad\\q" {}',
        "INVALID_STRING",
        '"Bad\\q"',
        SourceParseError,
    ),
    DiagnosticCase(
        "invalid-expression-string-escape",
        'module "M" { trigger "T" { Notification("bad\\q"); } }',
        "INVALID_STRING",
        '"bad\\q"',
        SourceParseError,
    ),
    *RAW_PAYLOAD_CASES,
    DiagnosticCase(
        "finite-float32-overflow",
        'module "M" { global x: float = 1.0e100; }',
        "FLOAT_OUT_OF_RANGE",
        "1.0e100",
        SourceBindingError,
    ),
    DiagnosticCase(
        "float-exponent-infinity",
        'module "M" { global x: float = 1.0e1000; }',
        "FLOAT_OUT_OF_RANGE",
        "1.0e1000",
        SourceBindingError,
    ),
    DiagnosticCase(
        "int32-underflow",
        'module "M" { trigger "T" { let x: int = -2147483649; } }',
        "INT_OUT_OF_RANGE",
        "-2147483649",
        SourceBindingError,
    ),
    DiagnosticCase(
        "raw-constant-int32-overflow",
        'module "M" { trigger "T" { let x: int = raw_expression int 1 { constant 9999999999999; '
        "}; } }",
        "INT_OUT_OF_RANGE",
        "9999999999999",
        SourceBindingError,
    ),
    DiagnosticCase(
        "oversized-integer",
        f'module "M" {{ global x: int = {"9" * 4301}; }}',
        "INVALID_NUMBER",
        "9" * 4301,
        SourceParseError,
    ),
    DiagnosticCase(
        "wrong-return-type",
        'module "M" { trigger "T" { let x: string = ThisCard(); } }',
        "SOURCE_TYPE_MISMATCH",
        "ThisCard",
        SourceBindingError,
    ),
    DiagnosticCase(
        "wrong-bare-expression-type",
        'module "M" { trigger "T" { let x: bool = ThisCard; } }',
        "SOURCE_TYPE_MISMATCH",
        "ThisCard",
        SourceBindingError,
    ),
    DiagnosticCase(
        "wrong-named-constant-type",
        'module "M" { trigger "T" { let x: bool = Constants.Conversation.ENCOURAGE; } }',
        "SOURCE_TYPE_MISMATCH",
        "Constants.Conversation.ENCOURAGE",
        SourceBindingError,
    ),
    DiagnosticCase(
        "nested-arity-error",
        'module "M" { trigger "T" { let x: string = (ThisCard(1)).FullName; } }',
        "EXPRESSION_ARITY",
        "ThisCard",
        SourceBindingError,
    ),
    DiagnosticCase(
        "nested-undefined-variable",
        'module "M" { trigger "T" { let x: string = variable("missing").FullName; } }',
        "UNDEFINED_VARIABLE",
        'variable("missing")',
        SourceBindingError,
    ),
    DiagnosticCase(
        "nested-unknown-expression",
        'module "M" { trigger "T" { let x: string = UnknownExpr().FullName; } }',
        "UNKNOWN_EXPRESSION_NAME",
        "UnknownExpr",
        SourceBindingError,
    ),
)


def _diagnostic_from_error(error: Exception) -> tuple[str, int, int, str]:
    if isinstance(error, SourceParseError):
        return error.filename, error.line, error.column, error.code
    assert isinstance(error, SourceBindingError)
    diagnostic = error.diagnostic
    return diagnostic.filename, diagnostic.line, diagnostic.column, diagnostic.code


def _expected(case):
    line, column = case.line_column
    return f"{case.name}.aa2m", line, column, case.code


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_source_diagnostics_report_exact_code_and_location(case):
    filename, line, column, code = _expected(case)

    result = validate_source(case.source, filename=filename)

    (diagnostic,) = result.diagnostics
    assert (diagnostic.filename, diagnostic.line, diagnostic.column, diagnostic.code) == (
        filename,
        line,
        column,
        code,
    )


@pytest.mark.parametrize(
    "case",
    [
        case
        for case in CASES
        if case.name in {"invalid-expression-string-escape", "wrong-return-type"}
    ],
    ids=lambda case: case.name,
)
def test_public_apis_agree_on_a_diagnostic(case):
    expected = _expected(case)
    filename = expected[0]
    with pytest.raises(case.error_type) as parsed:
        parse_module(case.source, filename=filename)
    assert _diagnostic_from_error(parsed.value) == expected
    if case.error_type is SourceParseError:
        with pytest.raises(SourceParseError) as syntax:
            parse_source_ast(case.source, filename=filename)
        assert _diagnostic_from_error(syntax.value) == expected

    with pytest.raises(CompileError) as compiled:
        compile_source(case.source, filename=filename)
    (diagnostic,) = compiled.value.diagnostics
    assert (diagnostic.filename, diagnostic.line, diagnostic.column, diagnostic.code) == expected


def test_int32_boundary_literals_compile_to_their_exact_bytes():
    source = 'module "M" { global low: int = -2147483648; global high: int = 2147483647; }'

    def text(value: str) -> bytes:
        return struct.pack("<I", len(value)) + value.encode("utf-16-le")

    def int_global(name: str, value: int) -> bytes:
        return struct.pack("<i", 1) + text(name) + struct.pack("<iiiiB", 1, value, 1, value, 0)

    # Native layout: name, description, no triggers, two INT globals, no dependencies.
    expected = (
        text("M")
        + struct.pack("<III", 0, 0, 2)
        + int_global("low", -(2**31))
        + int_global("high", 2**31 - 1)
        + struct.pack("<I", 0)
    )
    assert compile_source(source) == expected
