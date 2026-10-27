"""Diagnostic rendering: golden human snippets, short form, breadcrumbs and color rules."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from aa2modulus.binary.writer import encode_module
from aa2modulus.cli.render.breadcrumb import breadcrumb
from aa2modulus.cli.render.diagnostics import count_text, render_diagnostic, render_diagnostics
from aa2modulus.cli.render.snippets import SourceTexts, snippet_lines
from aa2modulus.cli.render.terminal import (
    ASCII_SEPARATOR,
    RenderOptions,
    ReportSettings,
    render_options,
    use_color,
)
from aa2modulus.core.diagnostics import Diagnostic
from aa2modulus.core.locations import RelatedLocation, SourceSpan
from aa2modulus.model.records import ActionCall, Expression, GuiAction, Module, Trigger, Variable
from aa2modulus.model.types import EXPR_CONSTANT, ValueType
from aa2modulus.model.values import Value
from tests.support.cli import invoke_cli

PLAIN = RenderOptions()


class FakeStream(io.StringIO):
    def __init__(self, tty: bool) -> None:
        super().__init__()
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


def located(
    line: int, column: int, end_column: int | None, text: str = "f.aa2m", **fields
) -> Diagnostic:
    return Diagnostic(
        text,
        line,
        column,
        fields.pop("severity", "error"),
        fields.pop("code", "SOME_CODE"),
        fields.pop("message", "something is wrong"),
        source_span=SourceSpan(text, line, column, line, end_column),
        **fields,
    )


def render(diagnostic: Diagnostic, source: str, options: RenderOptions = PLAIN) -> str:
    return render_diagnostic(diagnostic, options=options, sources={diagnostic.filename: source})


def test_human_snippet_with_gutter_carets_notes_and_help():
    source = 'module "M" {\n    let x = missing;\n}\n'
    diagnostic = located(
        2,
        13,
        19,
        code="UNDEFINED_VARIABLE",
        message="undefined variable 'missing'",
        notes=('in trigger "T"',),
        help="declare it with 'let missing: int = 0;'",
    )

    assert render(diagnostic, source) == (
        "error[UNDEFINED_VARIABLE]: undefined variable 'missing'\n"
        " --> f.aa2m:2:13\n"
        "  |\n"
        "2 |     let x = missing;\n"
        "  |             ^^^^^^^\n"
        "  |\n"
        '  = note: in trigger "T"\n'
        "  = help: declare it with 'let missing: int = 0;'"
    )


def test_tabs_expand_and_wide_characters_take_two_columns():
    tab_line, tab_carets = snippet_lines("\t\tlet x = a;", 11, 11)
    assert tab_line == "        let x = a;"
    assert tab_carets == " " * 16 + "^"

    wide_line, wide_carets = snippet_lines("let 日本 = bad;", 11, 13)
    assert wide_line == "let 日本 = bad;"
    # "let " is 4 columns, two wide characters 4 more, then " = b" puts "a" at column 12.
    assert wide_carets == " " * 12 + "^^^"
    _, wide_span_carets = snippet_lines("let 日本 = bad;", 5, 6)
    assert wide_span_carets == " " * 4 + "^" * 4


def test_long_lines_are_clipped_around_the_span():
    line = "x" * 150 + "BAD" + "y" * 150
    shown, carets = snippet_lines(line, 151, 153)

    assert shown.startswith("...") and shown.endswith("...")
    assert len(shown) < 140
    assert shown[carets.index("^") : carets.rindex("^") + 1] == "BAD"
    assert carets.count("^") == 3

    short, short_carets = snippet_lines("abc", 2, 2)
    assert (short, short_carets) == ("abc", " ^")


def test_related_locations_get_their_own_snippets():
    source = "macro twice(x) {\n  ok();\n}\ntwice(missing);\n"
    diagnostic = located(
        4,
        7,
        13,
        message="bad argument",
        related=(RelatedLocation(SourceSpan("f.aa2m", 1, 7, 1, 11), "macro defined here"),),
    )

    assert render(diagnostic, source) == (
        "error[SOME_CODE]: bad argument\n"
        " --> f.aa2m:4:7\n"
        "  |\n"
        "4 | twice(missing);\n"
        "  |       ^^^^^^^\n"
        "  |\n"
        "note: macro defined here\n"
        " --> f.aa2m:1:7\n"
        "  |\n"
        "1 | macro twice(x) {\n"
        "  |       ^^^^^"
    )


def test_missing_source_and_out_of_range_lines_render_without_a_snippet(tmp_path: Path):
    diagnostic = located(9, 2, 4, text=str(tmp_path / "gone.aa2m"))
    text = render_diagnostic(diagnostic, options=PLAIN)
    assert text.splitlines()[1] == f" --> {tmp_path / 'gone.aa2m'}:9:2"
    assert len(text.splitlines()) == 2

    real = tmp_path / "real.aa2m"
    real.write_text("one\ntwo\n", encoding="utf-8")
    from_disk = render_diagnostic(located(2, 1, 3, text=str(real)), options=PLAIN)
    assert "2 | two\n  | ^^^" in from_disk
    beyond = render_diagnostic(located(40, 1, 1, text=str(real)), options=PLAIN)
    assert len(beyond.splitlines()) == 2
    assert render_diagnostic(located(1, 1, 1, text="<stdout>"), options=PLAIN).count("\n") == 1


def test_short_form_is_stable_and_equals_str():
    diagnostic = located(
        2,
        13,
        19,
        code="UNDEFINED_VARIABLE",
        message="undefined variable 'missing'",
        notes=("ignored in short form",),
        related=(RelatedLocation(SourceSpan("f.aa2m", 1, 1), "declared here"),),
    )
    short = RenderOptions(format="short")

    assert render(diagnostic, "", short) == str(diagnostic)
    assert str(diagnostic) == (
        "f.aa2m:2:13: error[UNDEFINED_VARIABLE]: undefined variable 'missing'\n"
        "f.aa2m:1:1: note: declared here"
    )


def test_verbose_adds_offset_and_structural_path():
    diagnostic = located(1, 1, 1, path=("module", "triggers", 0), offset=0x1F4A)
    human = render(diagnostic, "x", RenderOptions(verbose=True))
    assert "= offset: 0x1F4A" in human
    assert "= path: module.triggers[0]" in human
    short = render(diagnostic, "x", RenderOptions(format="short", verbose=True))
    assert short.endswith("evidence: offset 0x1F4A, path module.triggers[0]")


def binary_module() -> Module:
    condition = Expression(ValueType.BOOL, EXPR_CONSTANT, constant=Value.boolean(True))
    return Module(
        "M", triggers=(Trigger("NPC Flag", gui_actions=(GuiAction(ActionCall(2, (condition,))),)),)
    )


BINARY_PATH = ("module", "triggers", 0, "gui_actions", 0, "action", "parameters", 0, "return_type")


def test_binary_only_diagnostic_shows_a_breadcrumb_and_hex_offset():
    diagnostic = Diagnostic(
        "MODULE", 1, 1, "error", "SOME_CODE", "bad return type", BINARY_PATH, offset=0x1F4A
    )

    assert diagnostic.is_binary_only
    assert render_diagnostic(diagnostic, options=PLAIN, module=binary_module()) == (
        "error[SOME_CODE]: bad return type\n"
        " --> MODULE (offset 0x1F4A)\n"
        '  = in: trigger "NPC Flag" › action 1 › parameter 1 › return type'
    )
    assert str(diagnostic) == "MODULE@0x1F4A: error[SOME_CODE]: bad return type"
    assert "return type" in render_diagnostic(diagnostic, options=PLAIN)


def test_breadcrumb_names_actions_with_metadata_and_falls_back_to_fields(metadata):
    resolved = metadata.resolve_module(binary_module())
    named = breadcrumb(BINARY_PATH, module=resolved)
    assert named.startswith('trigger "NPC Flag" › ')
    assert named.endswith("› return type")
    assert "action 1" not in named

    assert breadcrumb(BINARY_PATH, separator=ASCII_SEPARATOR) == (
        "trigger 1 > action 1 > parameter 1 > return type"
    )
    assert breadcrumb(("module", "globals", 2, "name")) == "global 3 › name"
    declared = Module(
        "M",
        dependencies=("Provider",),
        triggers=(
            Trigger(
                "T",
                variables=(
                    Variable(
                        ValueType.INT,
                        "x",
                        Expression(ValueType.INT, EXPR_CONSTANT, constant=Value.integer(1)),
                    ),
                ),
            ),
        ),
    )
    assert breadcrumb(("module", "dependencies", 0), module=declared) == 'dependency "Provider"'
    assert breadcrumb(("module", "dependencies", 0)) == "dependency 1"
    assert breadcrumb(("module", "triggers", 0, "variables", 0), module=declared) == (
        'trigger "T" › local "x"'
    )
    assert breadcrumb(("module", "triggers", 0, "variables", 0)) == "trigger 1 › local 1"
    assert breadcrumb(("triggers", 9, "unknown_part", 4), module=binary_module()) == (
        "trigger 10 › unknown part 5"
    )
    assert breadcrumb(()) == "module"


def test_summary_and_multiple_diagnostics_layout():
    first = located(1, 1, 1, severity="error")
    second = located(1, 1, 1, severity="warning", code="OTHER")
    assert count_text([first, second, second]) == "1 error, 2 warnings"
    assert count_text([]) == ""

    text = render_diagnostics(
        [first, second], options=PLAIN, sources={"f.aa2m": "x"}, summary="done"
    )
    assert text.count("\n\n") == 2 and text.endswith("\n\ndone")
    short = render_diagnostics(
        [first, second], options=RenderOptions(format="short"), summary="done"
    )
    assert short.splitlines()[-1] == "done" and len(short.splitlines()) == 3


def test_color_markers_are_added_only_when_enabled():
    diagnostic = located(1, 1, 1)
    plain = render(diagnostic, "x")
    colored = render(diagnostic, "x", RenderOptions(color=True))

    assert "\x1b" not in plain
    assert "\x1b[1m\x1b[31merror[SOME_CODE]\x1b[0m" in colored
    assert colored.replace("\x1b[1m", "").replace("\x1b[0m", "").count("\x1b") == colored.count(
        "\x1b[3"
    )


@pytest.mark.parametrize(
    ("mode", "tty", "environ", "expected"),
    [
        ("auto", True, {}, True),
        ("auto", False, {}, False),
        ("auto", True, {"NO_COLOR": "1"}, False),
        ("auto", False, {"FORCE_COLOR": "1"}, True),
        ("auto", False, {"FORCE_COLOR": "0"}, False),
        ("auto", True, {"FORCE_COLOR": ""}, True),
        ("auto", True, {"NO_COLOR": ""}, True),
        ("auto", True, {"TERM": "dumb"}, False),
        ("auto", False, {"FORCE_COLOR": "1", "TERM": "dumb"}, True),
        ("auto", False, {"FORCE_COLOR": "1", "NO_COLOR": "1"}, False),
        ("always", False, {"NO_COLOR": "1"}, True),
        ("never", True, {"FORCE_COLOR": "1"}, False),
    ],
)
def test_color_decision_follows_mode_then_environment(mode, tty, environ, expected, monkeypatch):
    monkeypatch.setattr(
        "aa2modulus.cli.render.terminal._enable_virtual_terminal", lambda stream: True
    )
    assert use_color(mode, FakeStream(tty), environ=environ) is expected


def test_windows_console_without_vt_support_stays_plain(monkeypatch):
    monkeypatch.setattr(
        "aa2modulus.cli.render.terminal._enable_virtual_terminal", lambda stream: False
    )
    assert use_color("auto", FakeStream(True), environ={}) is False
    assert use_color("always", FakeStream(True), environ={}) is True


def test_render_options_resolve_per_stream(monkeypatch):
    monkeypatch.setattr(
        "aa2modulus.cli.render.terminal._enable_virtual_terminal", lambda stream: True
    )
    settings = ReportSettings(format="short", verbose=True)
    options = render_options(settings, FakeStream(True), environ={"TERM": "xterm"})
    assert options == RenderOptions(format="short", color=True, verbose=True)

    class Ascii(FakeStream):
        encoding = "ascii"

    assert render_options(settings, Ascii(False), environ={}).separator == ASCII_SEPARATOR


def test_source_texts_prefer_supplied_text_over_disk(tmp_path: Path):
    path = tmp_path / "a.aa2m"
    path.write_text("disk\n", encoding="utf-8")
    texts = SourceTexts({str(path): "memory\r\nsecond"})
    assert texts.lines(str(path)) == ["memory", "second"]
    assert SourceTexts().lines(str(path)) == ["disk", ""]
    assert SourceTexts().lines(str(tmp_path)) is None
    assert SourceTexts().lines("bad\0name") is None


def test_cli_output_is_plain_when_piped_and_colored_on_request(tmp_path: Path, capsys):
    source = tmp_path / "bad.aa2m"
    source.write_text(
        'module "M" { trigger "T" { let x: string = ThisCard(); } }', encoding="utf-8"
    )

    piped = invoke_cli(capsys, "validate", str(source))
    colored = invoke_cli(capsys, "validate", str(source), "--color", "always")
    never = invoke_cli(
        capsys, "validate", str(source), "--color", "never", "--diagnostic-format", "short"
    )

    assert piped.returncode == colored.returncode == never.returncode == 1
    assert "\x1b" not in piped.stderr and "\x1b" not in never.stderr
    assert "\x1b[31m" in colored.stderr
    assert piped.stdout == colored.stdout == never.stdout == ""
    assert "^^^^" in piped.stderr
    assert "validation failed: 1 error" in piped.stderr
    assert "^" not in never.stderr


def test_decompile_reports_trailing_bytes_as_a_binary_warning(tmp_path: Path, capsys):
    module = tmp_path / "trailing"
    data = encode_module(Module("M"))
    module.write_bytes(data + b"\xaa\xbb")

    result = invoke_cli(capsys, "decompile", str(module), "-o", str(tmp_path / "out.aa2m"))

    assert result.returncode == 0
    assert "warning[TRAILING_BYTES]" in result.stderr
    assert f"(offset 0x{len(data):X})" in result.stderr
    assert "with 1 warning" in result.stderr


def test_binary_decode_errors_use_the_breadcrumb_form(tmp_path: Path, capsys):
    module = tmp_path / "broken"
    module.write_bytes(b"\x01\x02")

    for command in ("inspect", "decompile"):
        result = invoke_cli(capsys, command, str(module))
        assert result.returncode == 1
        assert result.stdout == ""
        assert "error[DECODE_ERROR]" in result.stderr
        assert f"--> {module} (offset 0x" in result.stderr

    short = invoke_cli(capsys, "inspect", str(module), "--diagnostic-format", "short")
    assert f"{module}@0x" in short.stderr


def test_inspect_prints_diagnostics_as_readable_breadcrumbs(tmp_path: Path, capsys):
    module = tmp_path / "undefined"
    module.write_bytes(
        encode_module(
            Module(
                "M",
                triggers=(
                    Trigger(
                        "Reader",
                        gui_actions=(
                            GuiAction(
                                ActionCall(
                                    999,
                                )
                            ),
                        ),
                    ),
                ),
            )
        )
    )

    result = invoke_cli(capsys, "inspect", str(module))
    verbose = invoke_cli(capsys, "inspect", str(module), "--verbose")

    assert "error[UNKNOWN_ACTION]" in result.stdout
    assert 'at trigger "Reader" › action 1 › id, offset 0x' in result.stdout
    assert "module.triggers[0]" not in result.stdout
    assert "path module.triggers[0].gui_actions[0]" in verbose.stdout
