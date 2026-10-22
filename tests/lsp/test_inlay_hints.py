"""Parameter-name inlay hints from binder selections, and their protocol session."""

from __future__ import annotations

from lsprotocol import types

from aa2modulus.lsp.features.inlay_hints import inlay_hints
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.workspace.documents import SourceWorkspace
from tests.support.lsp_client import Client
from tests.support.lsp_workspace import analyze_workspace

SOURCE = """macro "debug" {
  param "text" string;
  param "level" int;
  WriteLog("DEBUG: " + text);
}
module "M" {
  trigger "T" {
    on CONVERSATION_END;
    let coach: card = ThisCard;
    coach.SetStyle(2);
    ThisCard.SetVirtue(ToInt("1"));
    if ThisCard.GetBool("Tutor", true) { debug("é😀", 3); }
    H.Start(coach, TriggeringCard);
    coach.AddLike(TriggeringCard, -5);
    let a: int = Text.FirstIndexOf("abc", "b");
    let b: int = Text.FirstIndexOf("abc", "b", 1);
    Notification(ToString(a), !false);
    raw_action 7(true);
  }
}
"""

WHOLE = types.Range(types.Position(0, 0), types.Position(10_000, 0))


def _snapshot(tmp_path, context, source: str = SOURCE):
    uri = (tmp_path / "root.aa2m").as_uri()
    workspace = SourceWorkspace()
    workspace.open(uri, source, 1)
    return analyze_workspace(workspace, uri, context)


def _hints(tmp_path, context, source: str = SOURCE, range_=WHOLE, encoding: str = "utf-16"):
    """``(label, following text)`` per hint, decoded from protocol positions."""

    codec = PositionCodec(source, encoding=encoding)
    result = []
    for hint in inlay_hints(_snapshot(tmp_path, context, source), range_, encoding):
        assert hint.kind == types.InlayHintKind.Parameter
        assert hint.padding_right is True
        offset = codec.offset(hint.position)
        result.append((hint.label, source[offset:].split(",")[0].split(")")[0]))
    return result


def test_literal_arguments_are_labeled_from_the_selected_target(tmp_path, context):
    assert _hints(tmp_path, context) == [
        # Member forms name explicit arguments; the receiver is never labeled,
        # nor is a string storage key.
        ("fallback:", "true"),
        # Macro parameters.
        ("text:", '"é😀"'),
        ("level:", "3"),
        ("amount:", "-5"),
        # Each overload shows its own policy names.
        ("text:", '"abc"'),
        ("search:", '"b"'),
        ("text:", '"abc"'),
        ("search:", '"b"'),
        ("start:", "1"),
        # A negated literal is a literal; computed arguments are not.
        ("isImportant:", "!false"),
    ]


def test_lone_generic_or_callee_named_parameters_are_not_labeled(tmp_path, context):
    labels = {label for label, _ in _hints(tmp_path, context)}
    # coach.SetStyle(2) (style), SetVirtue (virtue) and ToInt("1") (value).
    assert not labels & {"style:", "virtue:", "value:"}
    source = 'module "M" { trigger "T" { on CARD_ADDED; let a: bool = Math.Roll(50); } }'
    assert _hints(tmp_path, context, source) == [("chance:", "50")]


def test_string_storage_keys_name_themselves(tmp_path, context):
    source = (
        'module "M" { trigger "T" { on CARD_ADDED; let k: string = "x";\n'
        'ClassStorage.SetInt("count", 3);\n'
        "ThisCard.SetInt(k, 4);\n"
        'let n: int = ClassStorage.GetInt("count", 0);\n'
        "} }\n"
    )
    # Flat ClassStorage slots are named "key"; card members carry the key role.
    assert _hints(tmp_path, context, source) == [
        ("value:", "3"),
        ("value:", "4"),
        ("fallback:", "0"),
    ]


def test_unresolved_calls_and_other_ranges_get_no_hints(tmp_path, context):
    source = (
        'module "M" { trigger "T" { on CARD_ADDED;\n'
        "Missing(1, 2);\n"
        'let b: bool = ThisCard.GetBool("x", true);\n'
        "} }\n"
    )
    # The document has an error, so hints come from the authoring view.
    assert _hints(tmp_path, context, source) == [("fallback:", "true")]
    line_one = types.Range(types.Position(1, 0), types.Position(1, 20))
    assert _hints(tmp_path, context, source, line_one) == []


def test_positions_follow_the_negotiated_encoding(tmp_path, context):
    source = (
        'module "M" { trigger "T" { on CARD_ADDED; WriteLog("é😀"); Notification("x", true); } }'
    )
    columns = {}
    for encoding in ("utf-8", "utf-16", "utf-32"):
        hints = inlay_hints(_snapshot(tmp_path, context, source), WHOLE, encoding)
        columns[encoding] = hints[-1].position.character
        assert _hints(tmp_path, context, source, encoding=encoding)[-1] == ("isImportant:", "true")
    # isImportant follows "é😀": 6 UTF-8 bytes, 3 UTF-16 units, 2 code points.
    assert columns["utf-8"] - columns["utf-16"] == 3
    assert columns["utf-16"] - columns["utf-32"] == 1


def test_session_advertises_and_answers_inlay_hints(tmp_path):
    client = Client()
    try:
        assert client.initialized["capabilities"]["inlayHintProvider"]
        uri = (tmp_path / "root.aa2m").as_uri()
        client.open(uri, SOURCE)
        result = client.request(
            "textDocument/inlayHint",
            {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": 11, "character": 0},
                    "end": {"line": 12, "character": 0},
                },
            },
        )
        assert [item["label"] for item in result] == ["fallback:", "text:", "level:"]
        assert result[0] == {
            "position": {"line": 11, "character": SOURCE.splitlines()[11].index("true")},
            "label": "fallback:",
            "kind": 2,
            "paddingRight": True,
        }
        client.finish()
    finally:
        if client.process.poll() is None:
            client.process.terminate()
            client.process.wait(timeout=10)
