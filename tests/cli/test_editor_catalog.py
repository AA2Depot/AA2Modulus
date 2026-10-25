"""``editor-catalog`` writes the catalog as UTF-8 bytes and its report to stderr."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from aa2modulus.app.editor_catalog.document import SCHEMA, editor_catalog, render
from aa2modulus.cli.common import EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR, EXIT_OK
from aa2modulus.cli.main import main
from aa2modulus.metadata.schema import MetadataError
from tests.support.paths import ROOT


@pytest.fixture(scope="module")
def expected() -> bytes:
    return render(editor_catalog()[0]).encode("utf-8")


def test_stdout_is_utf8_json_under_a_legacy_console_encoding(expected):
    environment = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run(
        [sys.executable, "-m", "aa2modulus", "editor-catalog"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
    )
    assert result.returncode == EXIT_OK, result.stderr
    assert result.stdout == expected
    assert b"\r\n" not in result.stdout
    assert json.loads(result.stdout)["schema"] == SCHEMA
    assert b"entries: action=" in result.stderr


def test_output_file_creates_parents_and_keeps_stdout_empty(expected, tmp_path, capsys):
    output = tmp_path / "docs" / "generated" / "builtins.json"

    assert main(["editor-catalog", "--output", str(output)]) == EXIT_OK
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "omitted examples:" in captured.err
    assert f"to {output}" in captured.err
    assert output.read_bytes() == expected


def test_output_write_failure_is_input_error(tmp_path, capsys):
    output = tmp_path / "builtins.json"
    output.mkdir()

    assert main(["editor-catalog", "-o", str(output)]) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"could not write catalog {output}" in captured.err


def test_metadata_failure_is_internal_error(monkeypatch, capsys):
    def broken_catalog():
        raise MetadataError("broken registry")

    monkeypatch.setattr("aa2modulus.cli.commands.editor_catalog.editor_catalog", broken_catalog)

    assert main(["editor-catalog"]) == EXIT_INTERNAL_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "metadata error: broken registry" in captured.err
