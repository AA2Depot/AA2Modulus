"""Negotiated LSP positions and inclusive parser spans."""

from __future__ import annotations

import pytest
from lsprotocol.types import Position, Range

from aa2modulus.core.locations import SourceSpan
from aa2modulus.lsp.protocol.positions import PositionCodec


@pytest.mark.parametrize(
    ("encoding", "expected"),
    [("utf-8", 5), ("utf-16", 3), ("utf-32", 2)],
)
def test_position_uses_negotiated_units_for_astral_unicode(encoding, expected):
    codec = PositionCodec("a😀b", encoding=encoding)

    position = codec.position(2)

    assert position == Position(line=0, character=expected)
    assert codec.offset(position) == 2


def test_utf16_and_utf8_interior_positions_round_down_to_codepoint_start():
    utf16 = PositionCodec("😀", encoding="utf-16")
    utf8 = PositionCodec("😀", encoding="utf-8")

    assert utf16.offset(Position(line=0, character=1)) == 0
    assert utf8.offset(Position(line=0, character=2)) == 0


@pytest.mark.parametrize(
    ("text", "offsets", "positions"),
    [
        ("a\nb", [0, 1, 2, 3], [(0, 0), (0, 1), (1, 0), (1, 1)]),
        ("a\r\nb", [0, 1, 2, 3, 4], [(0, 0), (0, 1), (0, 1), (1, 0), (1, 1)]),
        ("a\rb", [0, 1, 2, 3], [(0, 0), (0, 1), (1, 0), (1, 1)]),
    ],
)
def test_offsets_follow_lsp_line_endings_and_clamp_inside_breaks(text, offsets, positions):
    codec = PositionCodec(text)

    assert [
        (codec.position(offset).line, codec.position(offset).character) for offset in offsets
    ] == positions


def test_offset_clamps_invalid_lines_and_characters_to_line_end():
    codec = PositionCodec("abc\ndef")

    assert codec.offset(Position(line=0, character=2)) == 2
    assert codec.offset(Position(line=900, character=900)) == len("abc\ndef")
    assert codec.offset(Position(line=900, character=0)) == len("abc\ndef")
    assert codec.position(-1) == Position(line=0, character=0)
    assert codec.position(10_000) == Position(line=1, character=3)


def test_range_maps_one_based_inclusive_multiline_parser_span():
    codec = PositionCodec("a😀\nxy")

    assert codec.range(SourceSpan("x", 1, 2, 2, 1)) == Range(
        start=Position(line=0, character=1), end=Position(line=1, character=1)
    )


def test_range_handles_missing_end_and_eof_insertion_point():
    codec = PositionCodec("abc")

    assert codec.range(SourceSpan("x", 1, 2)) == Range(
        start=Position(line=0, character=1), end=Position(line=0, character=2)
    )
    assert codec.range(SourceSpan("x", 1, 99, 1, 99)) == Range(
        start=Position(line=0, character=3), end=Position(line=0, character=3)
    )
    assert codec.range(SourceSpan("x", 9, 1, 9, 1)) == Range(
        start=Position(line=0, character=3), end=Position(line=0, character=3)
    )


def test_range_retains_lark_lf_only_columns_for_bare_cr():
    codec = PositionCodec("a\rb\nq")

    assert codec.range(SourceSpan("x", 1, 3, 1, 3)) == Range(
        start=Position(line=1, character=0), end=Position(line=1, character=1)
    )


def test_range_rejects_non_source_spans_and_offsets_reject_nonintegers():
    codec = PositionCodec("abc")

    with pytest.raises(TypeError, match="SourceSpan"):
        codec.range("span")
    with pytest.raises(TypeError, match="integer"):
        codec.position(True)
    with pytest.raises(TypeError, match="integer"):
        codec.offset(Position(line=0, character=False))
    with pytest.raises(ValueError, match="encoding"):
        PositionCodec("x", encoding="ascii")
