"""The editor built-ins catalog: header, entries and the entries without an example."""

from __future__ import annotations

from typing import Any

import pytest

from aa2modulus.app.editor_catalog.document import editor_catalog
from aa2modulus.app.editor_catalog.entries import Report
from aa2modulus.context.operation import SourceContext


@pytest.fixture(scope="module")
def generated(context: SourceContext) -> tuple[dict[str, Any], Report]:
    return editor_catalog(context=context)


@pytest.fixture(scope="module")
def entries(generated: tuple[dict[str, Any], Report]) -> dict[str, dict[str, Any]]:
    return {entry["id"]: entry for entry in generated[0]["entries"]}


def by_name(entries: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    return next(entry for entry in entries.values() if entry["name"] == name)


def test_header_and_unique_ids(
    generated: tuple[dict[str, Any], Report], context: SourceContext
) -> None:
    document, _ = generated
    assert document["schema"] == "aa2modulus.editor-builtins.v1"
    assert document["languageVersion"] == context.source_policy.language_version
    assert document["catalogFingerprint"] == context.catalog.fingerprint
    assert document["website"] == "https://modulus.aa2d.net/"
    ids = [entry["id"] for entry in document["entries"]]
    assert len(ids) == len(set(ids))
    assert {entry["kind"] for entry in document["entries"]} == {
        "action",
        "event",
        "expression",
        "named_constant",
    }


def test_doc_path_is_the_entry_anchor_on_the_builtins_page(
    entries: dict[str, dict[str, Any]],
) -> None:
    assert entries["action-108"]["docPath"] == "reference/builtins/actions/general/#action-108"


def test_flat_member_and_value_entries(entries: dict[str, dict[str, Any]]) -> None:
    start = by_name(entries, "H.Start")
    assert [item["name"] for item in start["signatures"][0]["parameters"]] == ["pc", "partner"]
    assert start["signatures"][0]["label"] == "H.Start(pc: card, partner: card)"
    assert [(item["type"], item["role"]) for item in start["signatures"][0]["parameters"]] == [
        ("int", "card"),
        ("int", "card"),
    ]
    assert start["example"] == "H.Start(TriggeringCard, TriggeringCard);"

    like = by_name(entries, "<card>.AddLike")
    signature = like["signatures"][0]
    assert signature["receiver"] == {"role": "card", "type": "int"}
    assert signature["parameters"][0]["role"] == "card"
    assert signature["label"].startswith("<card>.AddLike(towards: card")

    response = by_name(entries, "Context.NpcCurrentResponse")
    assert response["valueEvents"] == ["NPC_RESPONSE"]
    assert response["example"] == "let value: int = Context.NpcCurrentResponse;"

    notification = by_name(entries, "Notification")
    defaults = {
        item["name"]: item["default"] for item in notification["signatures"][0]["parameters"]
    }
    assert defaults["isImportant"] == "false"


def test_report_has_no_missing_names(generated: tuple[dict[str, Any], Report]) -> None:
    assert generated[1].missing_names == []


def test_report_lines_list_each_section_with_its_entries() -> None:
    report = Report(
        counts={"action": 2, "event": 1},
        skipped=["action-1 (Set Variable): no canonical source spelling"],
        missing_names=["action-7"],
        omitted_examples=[("expression-int-100", "declares bool")],
    )
    assert report.lines() == [
        "entries: action=2, event=1",
        "skipped (no canonical source spelling): 1",
        "  action-1 (Set Variable): no canonical source spelling",
        "targets without policy parameter names: 1",
        "  action-7",
        "omitted examples: 1",
        "  expression-int-100: declares bool",
    ]


def test_only_natively_diagnosed_entries_have_no_example(
    generated: tuple[dict[str, Any], Report], entries: dict[str, dict[str, Any]]
) -> None:
    # INT/100 declares bool (N6) and STRING/13 is natively defective (N12).
    assert sorted(entry_id for entry_id, entry in entries.items() if not entry["example"]) == [
        "expression-int-100",
        "expression-string-13",
    ]
    assert sorted(entry_id for entry_id, _ in generated[1].omitted_examples) == [
        "expression-int-100",
        "expression-string-13",
    ]
