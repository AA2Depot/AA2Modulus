"""Built-in Markdown pages and the ranked built-in search over editor catalog entries."""

from __future__ import annotations

import pytest

from aa2modulus.app.editor_catalog.document import editor_catalog
from aa2modulus.app.editor_catalog.pages import page, page_text
from aa2modulus.app.editor_catalog.search import search


@pytest.fixture(scope="module")
def entries():
    document, _ = editor_catalog()
    return {entry["id"]: entry for entry in document["entries"]}


def _entry(**fields):
    signature = {"label": "F()", "receiver": None, "parameters": [], "returns": None}
    entry = {
        "id": "action-1",
        "kind": "action",
        "name": "F",
        "nativeName": "Native",
        "aliases": [],
        "category": "General",
        "description": "",
        "signatures": [signature],
        "valueEvents": None,
        "example": None,
        "docPath": "reference/builtins/actions/general/#action-1",
    }
    return entry | fields


def _signature(label, *, parameters=(), returns=None):
    return {
        "label": label,
        "receiver": None,
        "parameters": [
            {"name": name, "type": "int", "role": None, "default": None} for name in parameters
        ],
        "returns": returns,
    }


def test_action_page_lists_parameters_defaults_and_example(entries):
    assert page(entries["action-108"], website=None) == (
        "# Notification\n\n"
        "```aa2m\nNotification(text: string, isImportant: bool = false)\n```\n\n"
        "Display the notification on the screen.\n\n"
        "**Parameters**\n\n"
        "- `text`: `string`\n"
        "- `isImportant`: `bool`, default `false`\n\n"
        '**Example**\n\n```aa2m\nNotification("text", false);\n```\n\n'
        "Native name: Notification (General). ID: `action-108`\n"
    )


def test_member_page_lists_card_receiver(entries):
    text = page(entries["action-10"], website=None)
    assert text.startswith("# \\<card\\>.SetStyle\n\n```aa2m\n<card>.SetStyle(style: int)\n```")
    assert "**Parameters**\n\n- Receiver: `int` (card)\n- `style`: `int` (value)\n\n" in text


def test_expression_page_shows_returns_and_value_events(entries):
    assert page(entries["expression-int-70"], website=None) == (
        "# Conversation.IsAnswering\n\n"
        "```aa2m\nConversation.IsAnswering -> int\n```\n\n"
        "¯\\\\\\_(\u00b4\\*-\\*\\`)\\_/¯\n\n"
        "**Returns**\n\n`int`\n\n"
        "Has a value only in: `PC_CONVERSATION_STATE_UPDATED`, "
        "`PC_CONVERSATION_LINE_UPDATED`\n\n"
        "**Example**\n\n```aa2m\nlet value: int = Conversation.IsAnswering;\n```\n\n"
        "Native name: Is Answering (Conversation). ID: `expression-int-70`\n"
    )


def test_named_constant_page_has_its_value_and_no_parameters(entries):
    assert page(entries["named-constant-int-1"], website=None) == (
        "# Constants.Relationship.LOVE\n\n"
        "```aa2m\nConstants.Relationship.LOVE: int = 0\n```\n\n"
        "Love points\n\n"
        "**Example**\n\n```aa2m\nlet value: int = Constants.Relationship.LOVE;\n```\n\n"
        "Native name: Love Points (Relationship). ID: `named-constant-int-1`\n"
    )


def test_several_signatures_group_parameters_and_share_returns():
    returns = {"type": "int", "role": None}
    entry = _entry(
        signatures=[
            _signature("F(a: int) -> int", parameters=["a"], returns=returns),
            _signature("F()"),
            _signature("F(b: int) -> int", parameters=["b"], returns=returns),
        ]
    )
    assert page(entry, website=None) == (
        "# F\n\n```aa2m\nF(a: int) -> int\nF()\nF(b: int) -> int\n```\n\n"
        "**Parameters**\n\n"
        "`F(a: int) -> int`\n\n- `a`: `int`\n\n"
        "`F(b: int) -> int`\n\n- `b`: `int`\n\n"
        "**Returns**\n\n`int`\n\n"
        "Native name: Native (General). ID: `action-1`\n"
    )


def test_prose_escapes_markdown_syntax_and_line_markers():
    entry = _entry(
        name="a_b",
        description="  x *y* [z] <w> | v\n- item\n  # head\n+ plus  \n",
        nativeName="N`ative",
        signatures=[_signature("")],
    )
    assert page(entry, website=None) == (
        "# a\\_b\n\n```aa2m\na_b\n```\n\n"
        "x \\*y\\* \\[z\\] \\<w\\> \\| v\n\\- item\n  \\# head\n\\+ plus\n\n"
        "Native name: N\\`ative (General). ID: `action-1`\n"
    )


def test_website_link_joins_doc_path_once():
    text = page(_entry(), website="https://example.test/docs//")
    assert text.endswith(
        "\n\n[View online documentation](https://example.test/docs/reference/builtins/actions/general/#action-1)\n"
    )


@pytest.mark.parametrize("path", ["/missing.md", "/a/b.md", "/action-108.txt", "/x`y.md"])
def test_unknown_path_gets_an_unknown_builtin_page(entries, path):
    code = f"`` {path} ``" if "`" in path else f"`{path}`"
    assert page_text(entries, path, website=None) == (
        f"# Unknown built-in\n\nNo built-in documentation entry matches {code}.\n"
    )


@pytest.mark.parametrize("path", ["/action-108.md", "action-108.md"])
def test_page_path_selects_entry_by_id(entries, path):
    assert page_text(entries, path, website=None) == page(entries["action-108"], website=None)


@pytest.mark.parametrize(
    ("query", "first"),
    [
        ("notification", ["action-108"]),
        ("  Notification  ", ["action-108"]),
        ("StartHScene", ["action-51", "event-23"]),
        ("Start H", ["action-51", "event-23"]),
        ("virtue", ["expression-int-25", "action-32", "action-114"]),
    ],
)
def test_search_ranks_name_matches_first(entries, query, first):
    found = [entry["id"] for entry in search(list(entries.values()), query)]
    assert found[: len(first)] == first


def test_search_needs_every_token_and_keeps_catalog_order_without_tokens(entries):
    ordered = list(entries.values())
    assert search(ordered, "") == ordered
    assert search(ordered, "!!") == ordered
    assert search(ordered, "notification zzzz") == []
    ties = search([_entry(id="b", name="Same"), _entry(id="a", name="Same")], "same")
    assert [entry["id"] for entry in ties] == ["b", "a"]
