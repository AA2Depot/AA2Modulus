"""``editor-data`` writes the catalog or the lexicon as UTF-8 bytes and its report to stderr."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from aa2modulus.app.editor_catalog.document import SCHEMA, editor_catalog, render
from aa2modulus.app.editor_lexicon import SCHEMA as LEXICON_SCHEMA
from aa2modulus.app.editor_lexicon import editor_lexicon
from aa2modulus.cli.common import EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR, EXIT_OK, EXIT_USAGE_ERROR
from aa2modulus.cli.main import main
from aa2modulus.language.loader import load_language_policy
from aa2modulus.metadata.schema import MetadataError
from aa2modulus.syntax.lexicon import source_lexicon
from tests.support.paths import ROOT


@pytest.fixture(scope="module")
def expected() -> bytes:
    return render(editor_catalog()[0]).encode("utf-8")


def test_stdout_is_utf8_json_under_a_legacy_console_encoding(expected):
    environment = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run(
        [sys.executable, "-m", "aa2modulus", "editor-data", "catalog"],
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

    assert main(["editor-data", "catalog", "--output", str(output)]) == EXIT_OK
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "omitted examples:" in captured.err
    assert f"to {output}" in captured.err
    assert output.read_bytes() == expected


def test_lexicon_carries_the_fingerprint_the_server_advertises(metadata, capsysbinary):
    assert main(["editor-data", "lexicon"]) == EXIT_OK
    captured = capsysbinary.readouterr()
    document = json.loads(captured.out)
    assert captured.out == render(editor_lexicon()).encode("utf-8")
    assert document["schema"] == LEXICON_SCHEMA
    assert document["languageVersion"] == load_language_policy(metadata=metadata).language_version
    assert document["fingerprint"] == source_lexicon().fingerprint
    assert "import.trigger" in document["keywords"]


def test_lexicon_output_file_creates_parents(tmp_path, capsys):
    output = tmp_path / "generated" / "lexicon.json"

    assert main(["editor-data", "lexicon", "-o", str(output)]) == EXIT_OK
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"wrote lexicon {source_lexicon().fingerprint} to {output}" in captured.err
    assert json.loads(output.read_bytes())["schema"] == LEXICON_SCHEMA


@pytest.mark.parametrize("document", ["catalog", "lexicon"])
def test_output_write_failure_is_input_error(document, tmp_path, capsys):
    output = tmp_path / "data.json"
    output.mkdir()

    assert main(["editor-data", document, "-o", str(output)]) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"could not write {document} {output}" in captured.err


@pytest.mark.parametrize("arguments", [[], ["builtins"]])
def test_missing_or_unknown_document_is_usage_error(arguments, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["editor-data", *arguments])
    assert exit_info.value.code == EXIT_USAGE_ERROR
    assert "document" in capsys.readouterr().err


def test_editor_catalog_command_is_gone(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["editor-catalog"])
    assert exit_info.value.code == EXIT_USAGE_ERROR


def test_metadata_failure_is_internal_error(monkeypatch, capsys):
    def broken_catalog():
        raise MetadataError("broken registry")

    monkeypatch.setattr("aa2modulus.cli.commands.editor_data.editor_catalog", broken_catalog)

    assert main(["editor-data", "catalog"]) == EXIT_INTERNAL_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "metadata error: broken registry" in captured.err
