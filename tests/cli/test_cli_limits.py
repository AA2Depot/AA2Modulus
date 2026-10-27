"""CLI limit options reject input with shared, located diagnostics."""

from __future__ import annotations

import pytest

from aa2modulus.cli.common import EXIT_INPUT_ERROR, EXIT_OK
from aa2modulus.cli.main import main


@pytest.mark.parametrize(
    ("source_text", "options", "code"),
    [
        ('module "M" {}', ["--max-source-chars", "12"], "SOURCE_SIZE_LIMIT"),
        ('module "M" {}', ["--max-source-nodes", "2"], "SOURCE_NODE_LIMIT"),
        (
            'module "M" { trigger "T" { let first: int = 1; let second: int = 2; } }',
            ["--max-binding-work", "1"],
            "SOURCE_BINDING_WORK_LIMIT",
        ),
        (
            'module "M" { trigger "T" { Notification(' + "(" * 1200 + '"x"' + ")" * 1200 + "); } }",
            [],
            "SOURCE_DEPTH_LIMIT",
        ),
        (
            'module "M" { trigger "T" { Notification("x"); } }',
            ["--max-source-nesting", "1"],
            "SOURCE_NESTING_LIMIT",
        ),
        (
            'macro "log" { WriteLog("x"); } module "M" { trigger "T" { log(); } }',
            ["--max-macro-nodes", "1"],
            "MACRO_EXPANSION_LIMIT",
        ),
        (
            'macro "log" { WriteLog("x"); } module "M" { trigger "T" { log(); } }',
            ["--max-macro-depth", "0"],
            "MACRO_DEPTH_LIMIT",
        ),
    ],
    ids=["chars", "nodes", "binding-work", "syntax-depth", "nesting", "macro-nodes", "macro-depth"],
)
@pytest.mark.parametrize("command", ("validate", "compile"))
def test_source_limit_options_reject_input_with_located_diagnostics(
    source_text, options, code, command, tmp_path, capsys
):
    source = tmp_path / "limited.aa2m"
    source.write_text(source_text, encoding="utf-8")
    arguments = [command, str(source), *options]
    if command == "compile":
        arguments.extend(("--output", str(tmp_path / "module")))

    result = main(arguments)

    captured = capsys.readouterr()
    assert result == EXIT_INPUT_ERROR
    assert code in captured.out + captured.err
    assert f"{source}:1:" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        ("--max-syntax-depth", "513", "cannot exceed the supported ceiling of 512"),
        ("--max-source-nodes", "-1", "must be a nonnegative integer"),
        ("--max-binding-work", "-1", "must be a nonnegative integer"),
        ("--max-binding-errors", "0", "max_binding_errors must be at least 1"),
        ("--max-syntax-errors", "0", "max_syntax_errors must be at least 1"),
    ],
)
def test_invalid_limit_arguments_are_usage_errors(option, value, message, capsys):
    with pytest.raises(SystemExit) as raised:
        main(["validate", "missing.aa2m", option, value])

    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert captured.out == ""
    assert message in captured.err


def test_raised_source_nesting_limit_accepts_deeper_valid_input(tmp_path, capsys):
    source = tmp_path / "nested.aa2m"
    source.write_text(
        'module "M" { trigger "T" { ' + "loop {" * 65 + "}" * 65 + "} }",
        encoding="utf-8",
    )
    assert main(["validate", str(source)]) == EXIT_INPUT_ERROR
    assert "SOURCE_NESTING_LIMIT" in capsys.readouterr().err

    assert main(["validate", str(source), "--max-source-nesting", "65"]) == EXIT_OK
    assert "valid:" in capsys.readouterr().out


def test_independent_binding_errors_are_all_reported_and_capped(tmp_path, capsys):
    source = tmp_path / "errors.aa2m"
    source.write_text(
        'module "M" { trigger "T" {\nMissing();\nOther();\nThird();\n} }', encoding="utf-8"
    )

    assert main(["validate", str(source), "--diagnostic-format", "short"]) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert [line.split(": ")[0] for line in captured.err.splitlines()[:3]] == [
        f"{source}:{line}:1" for line in (2, 3, 4)
    ]
    assert "validation failed: 3 errors" in captured.err

    arguments = ["validate", str(source), "--diagnostic-format", "short"]
    assert main([*arguments, "--max-binding-errors", "2"]) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert "error[SOURCE_BINDING_ERROR_LIMIT]: binding stopped after 2 errors" in captured.err
    assert "validation failed: 3 errors" in captured.err


def test_independent_syntax_errors_are_all_reported_and_capped(tmp_path, capsys):
    source = tmp_path / "syntax.aa2m"
    source.write_text(
        'module "M" { trigger "T" {\nlet a: int = ;\nlet b: int = ;\nlet c: int = ;\n'
        "let d: int = ;\n} }",
        encoding="utf-8",
    )
    arguments = ["validate", str(source), "--diagnostic-format", "short"]

    assert main(arguments) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert captured.err.count("error[SYNTAX_ERROR]") == 4
    assert "SOURCE_SYNTAX_ERROR_LIMIT" not in captured.err

    assert main([*arguments, "--max-syntax-errors", "2"]) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert captured.err.count("error[SYNTAX_ERROR]") == 2
    assert captured.err.count("error[SOURCE_SYNTAX_ERROR_LIMIT]") == 1
    assert (
        "error[SOURCE_SYNTAX_ERROR_LIMIT]: syntax checking stopped after 2 errors" in captured.err
    )
    assert "validation failed: 3 errors" in captured.err
