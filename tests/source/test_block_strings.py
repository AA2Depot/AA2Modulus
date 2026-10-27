"""Block-string descriptions decode, report malformed blocks and survive decompile."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aa2modulus.decompile.format.text import description
from aa2modulus.syntax.parser.errors import SourceParseError
from tests.support.source import parse_module


def _module(block: str) -> str:
    return f'module "M" {{\n  description {block};\n}}\n'


@pytest.mark.parametrize(
    "block,expected",
    [
        ('"""\n    a\n    b\n    """', "a\r\nb"),
        ('"""\r\n    a\r\n    b\r\n    """', "a\r\nb"),
        ('"""  \n    a\n\n      b\n    """', "a\r\n\r\n  b"),
        ('"""\n    a\n  \n    """', "a\r\n"),
        ('"""\n    a "" ""\\"\n    """', 'a "" """'),
        ('"""\n    \\n\\r\\t\\u00e9\\u0020\n    """', "\n\r\té "),
        ('"""\n    """', ""),
    ],
    ids=["lf", "crlf", "deeper-indent", "short-blank", "quotes", "escapes", "empty"],
)
def test_block_lines_lose_the_closing_indent_and_join_with_crlf(block, expected, context):
    assert parse_module(_module(block), context=context).description == expected


@pytest.mark.parametrize(
    "block,position,message",
    [
        ('"""a\n    """', (2, 15), 'block string text starts on the line after `"""`'),
        ('"""\n    a"""', (2, 15), 'the closing `"""` must stand on its own line'),
        ('"""\n    a\n  b\n    """', (4, 1), 'line is indented less than the closing `"""`'),
        ('"""\n    a\\\n    """', (3, 1), "a block string line cannot end with `\\`"),
        ('"""\n    a\tb\n    """', (3, 1), "invalid JSON string: Invalid control character at"),
    ],
    ids=["opening-text", "closing-text", "under-indent", "trailing-backslash", "raw-tab"],
)
def test_malformed_blocks_report_invalid_string(block, position, message, context):
    with pytest.raises(SourceParseError) as raised:
        parse_module(_module(block), context=context)
    error = raised.value
    assert (error.code, (error.line, error.column), error.message) == (
        "INVALID_STRING",
        position,
        message,
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("a\nb", '"a\\nb"'),
        ("a\r\n\r\nb", '"""\n    a\n\n    b\n    """'),
        ("a\r\nb\nc", '"""\n    a\n    b\\nc\n    """'),
        ('"\r\n""\r\n"""\r\n""""', '"""\n    "\n    ""\n    ""\\"\n    ""\\""\n    """'),
        ("a \r\n\t", '"""\n    a\\u0020\n    \\t\n    """'),
        ("é\r\n\\", '"""\n    \\u00e9\n    \\\\\n    """'),
    ],
    ids=["no-crlf", "crlf", "lone-lf", "quote-runs", "trailing-space", "escapes"],
)
def test_descriptions_with_crlf_decompile_to_a_block(value, expected):
    assert description(value) == expected


_PIECES = st.sampled_from(["\r\n", "\r", "\n", '"', "\\", " ", "\t", "a", "é", "\x00"])


@given(value=st.lists(_PIECES).map("".join) | st.text())
def test_every_description_survives_decompile_and_parse(value, context):
    assert parse_module(_module(description(value)), context=context).description == value
