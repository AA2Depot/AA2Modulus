"""Semantic tokens from binder selections, declarations, the lexical scan and their session."""

from __future__ import annotations

from lsprotocol import types

from aa2modulus.lsp.features.semantic_tokens import TOKEN_MODIFIERS, TOKEN_TYPES, semantic_tokens
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.workspace.documents import SourceWorkspace
from tests.support.lsp_client import Client
from tests.support.lsp_workspace import analyze_workspace

GREET = """trigger "Greet" {
  slot "who" string;
  on CARD_ADDED;
  WriteLog(who);
}
"""

SOURCE = """import "greet.aa2mi";
const Tag: string = "Naive";
macro "debug" {
  param "text" string;
  WriteLog("DEBUG: " + text);
}
module "Tokens" {
  global day: int = 3;
  import.trigger "Greet" "Hello" { slot "who" = Tag; }
  trigger "T" {
    on CONVERSATION_END;
    let coach: card = ThisCard;
    coach.SetVirtue(3);
    day = Globals.CurrentDay + coach.Target.Virtue;
    let school: int = Constants.Room.SCHOOL_GATES + Constants.EventType.KEY_PRESS;
    variable("coach").AddLike(TriggeringCard, ToInt("1"));
    debug(const("Tag"));
    H.Start(coach, TriggeringCard);
    for day from 0 to 2 { raw_action 7(true); }
    if ThisCard.GetBool("Naive", true) { debug("é😀" + ThisCard.FullName); }
  }
}"""


def _decode(source: str, data: list[int], encoding: str) -> list[tuple[str, str, frozenset[str]]]:
    codec = PositionCodec(source, encoding=encoding)
    tokens = []
    line = character = 0
    for index in range(0, len(data), 5):
        delta_line, delta_start, length, kind, modifiers = data[index : index + 5]
        line += delta_line
        character = delta_start if delta_line else character + delta_start
        start = codec.offset(types.Position(line, character))
        end = codec.offset(types.Position(line, character + length))
        names = frozenset(name for bit, name in enumerate(TOKEN_MODIFIERS) if modifiers >> bit & 1)
        tokens.append((source[start:end], TOKEN_TYPES[kind], names))
    return tokens


def _data(tmp_path, context, source: str, encoding: str, name: str = "root.aa2m") -> list[int]:
    (tmp_path / "greet.aa2mi").write_text(GREET, encoding="utf-8")
    uri = (tmp_path / name).as_uri()
    workspace = SourceWorkspace()
    workspace.open(uri, source, 1, "aa2mi" if name.endswith(".aa2mi") else "aa2m")
    return semantic_tokens(analyze_workspace(workspace, uri, context), encoding).data


def _tokens(tmp_path, context, source: str = SOURCE, encoding: str = "utf-16", **extra):
    return _decode(source, _data(tmp_path, context, source, encoding, **extra), encoding)


def _kinds(tokens, text: str) -> list[tuple[str, frozenset[str]]]:
    return [(kind, modifiers) for name, kind, modifiers in tokens if name == text]


LIBRARY = frozenset({"defaultLibrary"})
CONSTANT = frozenset({"defaultLibrary", "readonly"})


def test_every_legend_row_comes_from_the_selected_target(tmp_path, context):
    tokens = _tokens(tmp_path, context)
    declaration = frozenset({"declaration"})
    assert _kinds(tokens, "Tag") == [
        ("variable", frozenset({"readonly", "declaration"})),
        ("variable", frozenset({"readonly"})),
    ]
    assert _kinds(tokens, '"debug"') == [("macro", declaration)]
    assert _kinds(tokens, "debug") == [("macro", frozenset())] * 2
    assert _kinds(tokens, '"text"') == [("parameter", declaration)]
    assert _kinds(tokens, "text") == [("parameter", frozenset())]
    assert _kinds(tokens, '"Greet"') == [("class", frozenset())]
    assert _kinds(tokens, '"who"') == [("parameter", frozenset())]
    assert _kinds(tokens, "WriteLog") == [("function", LIBRARY)]
    assert _kinds(tokens, "CONVERSATION_END") == [("event", LIBRARY)]
    assert _kinds(tokens, "day") == [
        ("variable", declaration),
        ("variable", frozenset({"modification"})),
        ("variable", frozenset({"modification"})),
    ]
    assert _kinds(tokens, "coach") == [("variable", declaration)] + [("variable", frozenset())] * 3
    assert _kinds(tokens, "ThisCard") == [("variable", CONSTANT)] * 3
    assert _kinds(tokens, "TriggeringCard") == [("variable", CONSTANT)] * 2
    assert _kinds(tokens, "SetVirtue") == [("method", LIBRARY)]
    assert _kinds(tokens, "GetBool") == [("method", LIBRARY)]
    assert _kinds(tokens, "AddLike") == [("method", LIBRARY)]
    assert _kinds(tokens, "Target") == [("property", LIBRARY)]
    assert _kinds(tokens, "Virtue") == [("property", LIBRARY)]
    assert _kinds(tokens, "FullName") == [("property", LIBRARY)]
    assert _kinds(tokens, "ToInt") == [("function", LIBRARY)]
    assert _kinds(tokens, "CurrentDay") == [("property", CONSTANT)]
    assert _kinds(tokens, "SCHOOL_GATES") == [("enumMember", CONSTANT)]  # verified value
    assert _kinds(tokens, "KEY_PRESS") == [("enumMember", CONSTANT)]  # native named constant
    assert _kinds(tokens, "Start") == [("function", LIBRARY)]
    namespaces = [name for name, kind, _ in tokens if kind == "namespace"]
    assert namespaces == ["Globals", "Constants", "Room", "Constants", "EventType", "H"]


def test_templates_and_slots_in_a_library(tmp_path, context):
    tokens = _tokens(tmp_path, context, GREET, name="greet.aa2mi")
    assert tokens == [
        ("trigger", "keyword", frozenset()),
        ('"Greet"', "class", frozenset({"declaration"})),
        ("slot", "keyword", frozenset()),
        ('"who"', "parameter", frozenset({"declaration"})),
        ("string", "type", frozenset()),
        ("on", "keyword", frozenset()),
        ("CARD_ADDED", "event", LIBRARY),
        ("WriteLog", "function", LIBRARY),
        ("who", "parameter", frozenset()),
    ]


def test_quoted_references_lexical_forms_and_unresolved_names(tmp_path, context):
    tokens = _tokens(tmp_path, context)
    # The quoted spelling is the name, so it carries the declaration's kind, not ``string``.
    assert _kinds(tokens, '"coach"') == [("variable", frozenset())]
    assert _kinds(tokens, '"Tag"') == [("variable", frozenset({"readonly"}))]
    assert _kinds(tokens, '"Greet"') == [("class", frozenset())]
    for text, kind in (
        ("raw_action", "keyword"),
        ("variable", "keyword"),
        ("const", "keyword"),
        ("import.trigger", "keyword"),
        ("true", "keyword"),
        ("card", "type"),
        ("7", "number"),
        ('"Naive"', "string"),
        ('"Tokens"', "string"),
        ("+", "operator"),
        ("=", "operator"),
    ):
        assert (kind, frozenset()) in _kinds(tokens, text), text
    dotted = {name for name, _, _ in tokens if "." in name}
    assert dotted == {"import.trigger", '"greet.aa2mi"'}

    # A typo binds to nothing, so it gets no token; the rest of the file keeps them.
    typo = _tokens(tmp_path, context, SOURCE.replace("coach.SetVirtue(3);", "WriteLog(Glob.X);"))
    assert {"Glob", "X"}.isdisjoint(name for name, _, _ in typo)
    assert _kinds(typo, "CurrentDay") == [("property", CONSTANT)]
    # The authoring view keeps tokens around a syntax error.
    broken = _tokens(tmp_path, context, SOURCE.replace("coach.SetVirtue(3);", "coach.(;"))
    assert "SetVirtue" not in {name for name, _, _ in broken}
    assert _kinds(broken, "CurrentDay") == [("property", CONSTANT)]
    assert _kinds(broken, "FullName") == [("property", LIBRARY)]
    assert _kinds(broken, "for") == [("keyword", frozenset())]


def test_float_bits_is_a_keyword_and_number_and_allow_codes_are_enum_members(tmp_path, context):
    source = (
        'module "M" { @allow(NATIVE_DEFECTIVE_EXPRESSION) trigger "T" { on CARD_ADDED;'
        " let f: float = float_bits(0x7fa00001); } }"
    )
    tokens = _tokens(tmp_path, context, source)
    assert _kinds(tokens, "float_bits") == [("keyword", frozenset())]
    assert _kinds(tokens, "0x7fa00001") == [("number", frozenset())]
    assert _kinds(tokens, "@allow") == [("decorator", frozenset())]
    assert _kinds(tokens, "NATIVE_DEFECTIVE_EXPRESSION") == [("enumMember", frozenset())]


def test_comments_and_strings_are_split_per_line_in_every_encoding(tmp_path, context):
    source = (
        'module "M" {\n  /* one 😀\n  two\n  three */\n  trigger "T" { on CARD_ADDED; // é😀\r'
        'still comment\n  WriteLog("é😀"); }\n}\n'
    )
    expected = None
    for encoding in ("utf-8", "utf-16", "utf-32"):
        tokens = _tokens(tmp_path, context, source, encoding=encoding)
        # A line comment runs to ``\n``, and a lone ``\r`` splits it.
        assert [name for name, kind, _ in tokens if kind == "comment"] == [
            "/* one 😀",
            "  two",
            "  three */",
            "// é😀",
            "still comment",
        ]
        assert ('"é😀"', "string", frozenset()) in tokens
        assert expected in (None, tokens)
        expected = tokens


def test_positions_use_the_negotiated_encoding(tmp_path, context):
    columns = {}
    for encoding in ("utf-8", "utf-16", "utf-32"):
        tokens = _tokens(tmp_path, context, encoding=encoding)
        assert tokens[-2:] == [
            ("ThisCard", "variable", CONSTANT),
            ("FullName", "property", LIBRARY),
        ]
        data = _data(tmp_path, context, SOURCE, encoding)
        column = 0
        for index in range(0, len(data), 5):
            column = data[index + 1] if data[index] else column + data[index + 1]
        columns[encoding] = column
    # FullName follows "é😀": 6 UTF-8 bytes, 3 UTF-16 units, 2 code points.
    assert columns["utf-8"] - columns["utf-16"] == 3
    assert columns["utf-16"] - columns["utf-32"] == 1


LIBRARY_TEXT = "macro say { param message string; WriteLog(message); }\n"
ROOT_TEXT = 'import "library.aa2mi";\nmodule "Root" { trigger "T" { on CARD_ADDED; say("x"); } }\n'


def test_session_advertises_the_legend_and_refreshes_after_an_import_changes(tmp_path):
    library = tmp_path / "library.aa2mi"
    root = tmp_path / "root.aa2m"
    library.write_text(LIBRARY_TEXT, encoding="utf-8")
    root.write_text(ROOT_TEXT, encoding="utf-8")
    client = Client(capabilities={"workspace": {"semanticTokens": {"refreshSupport": True}}})
    try:
        provider = client.initialized["capabilities"]["semanticTokensProvider"]
        # Earlier legend indices stay the same; new types are appended.
        assert TOKEN_TYPES[:10] == (
            "namespace",
            "function",
            "method",
            "property",
            "enumMember",
            "event",
            "variable",
            "parameter",
            "macro",
            "class",
        )
        assert provider["legend"] == {
            "tokenTypes": list(TOKEN_TYPES),
            "tokenModifiers": list(TOKEN_MODIFIERS),
        }
        assert provider["full"] is True
        assert "range" not in provider

        client.open(root.as_uri(), ROOT_TEXT)
        client.open(library.as_uri(), LIBRARY_TEXT, language_id="aa2mi")
        result = client.request(
            "textDocument/semanticTokens/full", {"textDocument": {"uri": root.as_uri()}}
        )
        decoded = _decode(ROOT_TEXT, result["data"], "utf-16")
        assert ("say", "macro", frozenset()) in decoded

        # The root's text is unchanged, but its macro is gone: ask for new tokens once.
        client.change(library.as_uri(), "// emptied\n", 2)
        client.respond("workspace/semanticTokens/refresh")
        result = client.request(
            "textDocument/semanticTokens/full", {"textDocument": {"uri": root.as_uri()}}
        )
        assert "say" not in {name for name, _, _ in _decode(ROOT_TEXT, result["data"], "utf-16")}
        client.finish()
    finally:
        if client.process.poll() is None:
            client.process.terminate()
            client.process.wait(timeout=10)
