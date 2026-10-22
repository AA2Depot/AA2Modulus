"""The editor ``builtins.json`` export: entries, compiled examples and ``--check``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aa2modulus.app.compile import compile_source
from aa2modulus.context.operation import SourceContext
from tools.editor_docs.entries import Report
from tools.export_editor_docs import (
    SCHEMA,
    build_editor_docs,
    check_output,
    main,
    render,
)


@pytest.fixture(scope="module")
def context() -> SourceContext:
    return SourceContext.create()


@pytest.fixture(scope="module")
def generated(context: SourceContext) -> tuple[dict[str, Any], Report]:
    return build_editor_docs(context=context)


@pytest.fixture(scope="module")
def entries(generated: tuple[dict[str, Any], Report]) -> dict[str, dict[str, Any]]:
    return {entry["id"]: entry for entry in generated[0]["entries"]}


def by_name(entries: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    return next(entry for entry in entries.values() if entry["name"] == name)


def test_header_and_unique_ids(
    generated: tuple[dict[str, Any], Report], context: SourceContext
) -> None:
    document, _ = generated
    assert document["schema"] == SCHEMA
    assert document["languageVersion"] == context.source_policy.language_version
    assert document["catalogFingerprint"] == context.catalog.fingerprint
    assert document["website"] is None
    ids = [entry["id"] for entry in document["entries"]]
    assert len(ids) == len(set(ids))
    assert {entry["kind"] for entry in document["entries"]} == {
        "action",
        "event",
        "expression",
        "named_constant",
    }


def test_flat_member_and_value_entries(entries: dict[str, dict[str, Any]]) -> None:
    start = by_name(entries, "H.Start")
    assert [item["name"] for item in start["signatures"][0]["parameters"]] == ["pc", "partner"]
    assert start["signatures"][0]["label"] == "H.Start(pc: card, partner: card)"
    assert [(item["type"], item["role"]) for item in start["signatures"][0]["parameters"]] == [
        ("int", "card"),
        ("int", "card"),
    ]
    assert start["example"]

    like = by_name(entries, "<card>.AddLike")
    signature = like["signatures"][0]
    assert signature["receiver"] == {"role": "card", "type": "int"}
    assert signature["parameters"][0]["role"] == "card"
    assert signature["label"].startswith("<card>.AddLike(towards: card")

    response = by_name(entries, "Context.NpcCurrentResponse")
    assert response["valueEvents"] == ["NPC_RESPONSE"]
    assert response["example"]

    notification = by_name(entries, "Notification")
    defaults = {
        item["name"]: item["default"] for item in notification["signatures"][0]["parameters"]
    }
    assert defaults["isImportant"] == "false"


def test_report_has_no_missing_names(generated: tuple[dict[str, Any], Report]) -> None:
    assert generated[1].missing_names == []
    assert generated[1].lines()


def test_examples_compile(
    generated: tuple[dict[str, Any], Report],
    entries: dict[str, dict[str, Any]],
    context: SourceContext,
) -> None:
    sample = [e for e in entries.values() if e["example"]][::25]
    assert len(sample) > 20
    for entry in sample:
        example = entry["example"]
        if entry["kind"] != "event":
            event = (entry["valueEvents"] or ["CARD_ADDED"])[0]
            example = f'trigger "Example" {{\n  on {event};\n  {example}\n}}'
        compile_source(f'module "Examples" {{\n{example}\n}}\n', context=context)


def test_check_detects_stale_file(generated: tuple[dict[str, Any], Report], tmp_path: Path) -> None:
    document = generated[0]
    path = tmp_path / "builtins.json"
    assert check_output(path, document) is not None
    path.write_text(render(document), encoding="utf-8", newline="\n")
    assert check_output(path, document) is None
    path.write_text(render(document).replace("H.Start", "H.Begin"), encoding="utf-8")
    assert check_output(path, document) is not None
    with pytest.raises(SystemExit) as exit:
        main(["--output", str(path), "--check"])
    assert exit.value.code == 1
