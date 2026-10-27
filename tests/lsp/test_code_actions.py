"""Quick fixes: published diagnostic data becomes code actions, filtered by kind and version."""

from __future__ import annotations

import pytest
from lsprotocol import types

from aa2modulus.lsp.protocol.diagnostics import quick_fixes
from aa2modulus.lsp.workspace.documents import SourceWorkspace
from tests.support.lsp_workspace import apply_edits, published_diagnostics

FLAT = 'module "M" { trigger "T" { on CARD_ADDED;\n  SetVirtue(ThisCard, 3);\n} }\n'
FIXED = 'module "M" { trigger "T" { on CARD_ADDED;\n  ThisCard.SetVirtue(3);\n} }\n'

# Two syntax errors: only the first, a mistaken `=`, has an exact rewrite.
SYNTAX = (
    'module "M" {\n  trigger "T" {\n    on CARD_ADDED;\n    let y: int = 1;\n'
    "    if y = 3 { }\n    y = ;\n  }\n}\n"
)
# A decompiled read of a variable the module never declares.
RECOVERED = (
    'module "Receiver" {\n  depends_on "Provider";\n\n  trigger "T" {\n    on CARD_ADDED;\n'
    '    raw_action 1(raw_expression int 2 { variable "counter"; }, 1);\n  }\n}\n'
)
RESERVED = 'module "M" {\n  trigger "T" {\n    on CARD_ADDED;\n    let import: int = 1;\n  }\n}\n'
CARD = (
    'module "Cards" { trigger "T" { on CARD_ADDED; let amount: int = 4; '
    "let coach: card = ThisCard; coach.AddLike(amount, coach); } }"
)
# A quoted global that collides with a constant makes the bare name ambiguous.
AMBIGUOUS = (
    'module "M" { global "K": int = 0; const K: int = 7; '
    'trigger "T" { on CARD_ADDED; WriteLog(ToString(K)); } }'
)

URI = "untitled:Fixes"


def _actions(context, source, *, version=1, document_changes=False):
    """The code actions for every diagnostic of ``source``, as a client echoes them."""

    workspace = SourceWorkspace()
    workspace.open(URI, source, 1)
    diagnostics = published_diagnostics(workspace, URI, context)
    return diagnostics, quick_fixes(URI, version, diagnostics, document_changes=document_changes)


@pytest.mark.parametrize(
    ("source", "titles", "fixed"),
    [
        (FLAT, ["Write 'ThisCard.SetVirtue(3)'"], FIXED),
        (
            'module "M" { trigger "T" { on CARD_ADDED; let a: int = globals.CurrentDay; } }',
            ["Change 'globals' to 'Globals'"],
            'module "M" { trigger "T" { on CARD_ADDED; let a: int = Globals.CurrentDay; } }',
        ),
        (
            'module "M" { global "ThisCard": int = 0; '
            'trigger "T" { on CARD_ADDED; ThisCard = 3; } }',
            ['Write variable("ThisCard")'],
            'module "M" { global "ThisCard": int = 0; '
            'trigger "T" { on CARD_ADDED; variable("ThisCard") = 3; } }',
        ),
        ('module "M" { trigger "T" { on CARD_ADDED; Missing(); } }', [], None),
        (
            SYNTAX,
            ["Use '=='"],
            SYNTAX.replace("if y = 3", "if y == 3"),
        ),
        (
            RECOVERED,
            ["Declare global 'counter'", "Declare global 'counter'"],
            RECOVERED.replace('  trigger "T"', '  global counter: int = 0;\n\n  trigger "T"'),
        ),
        (RESERVED, ["Write '\"import\"'"], RESERVED.replace("let import", 'let "import"')),
        (CARD, ["Write Card(amount)"], CARD.replace("(amount, coach)", "(Card(amount), coach)")),
        (
            AMBIGUOUS,
            ['Write const("K")', 'Write variable("K")'],
            AMBIGUOUS.replace("ToString(K)", 'ToString(const("K"))'),
        ),
    ],
)
def test_diagnostic_fixes_become_quick_fix_actions(context, source, titles, fixed):
    diagnostics, actions = _actions(context, source)

    assert [action.title for action in actions] == titles
    assert {action.kind for action in actions} <= {types.CodeActionKind.QuickFix}
    assert all(action.diagnostics[0] in diagnostics for action in actions)
    if fixed is None:
        assert all(diagnostic.data is None for diagnostic in diagnostics)
    else:
        assert apply_edits(source, actions[0].edit.changes[URI]) == fixed


def test_a_lone_fix_is_preferred_and_alternatives_are_not(context):
    _, lone = _actions(context, FLAT)
    _, alternatives = _actions(context, AMBIGUOUS)

    assert [action.is_preferred for action in lone] == [True]
    assert [action.is_preferred for action in alternatives] == [None, None]


def test_document_change_clients_get_edits_for_the_open_version(context):
    _, (action,) = _actions(context, FLAT, document_changes=True)

    assert action.edit.changes is None
    (change,) = action.edit.document_changes
    assert (change.text_document.uri, change.text_document.version) == (URI, 1)
    assert apply_edits(FLAT, change.edits) == FIXED


def test_fixes_computed_for_an_older_version_are_not_offered(context):
    diagnostics, actions = _actions(context, FLAT, version=2)

    assert diagnostics[0].data is not None
    assert actions == []


def _request(connection, uri, diagnostics, **extra):
    return connection.request(
        "textDocument/codeAction",
        {
            "textDocument": {"uri": uri},
            "range": diagnostics[0]["range"],
            "context": {"diagnostics": diagnostics, **extra},
        },
    )


_EDIT = {
    "range": {"start": {"line": 1, "character": 2}, "end": {"line": 1, "character": 25}},
    "newText": "ThisCard.SetVirtue(3);",
}


@pytest.mark.parametrize("fixture", ["client", "full_client"])
def test_code_action_request_answers_with_the_json_shape_the_client_negotiated(
    request, tmp_path, fixture
):
    connection = request.getfixturevalue(fixture)
    uri = (tmp_path / "root.aa2m").as_uri()
    connection.open(uri, FLAT)
    (diagnostic,) = connection.diagnostics(uri, bool, version=1)

    edit = (
        {"changes": {uri: [_EDIT]}}
        if fixture == "client"
        else {"documentChanges": [{"textDocument": {"uri": uri, "version": 1}, "edits": [_EDIT]}]}
    )
    assert _request(connection, uri, [diagnostic]) == [
        {
            "title": "Write 'ThisCard.SetVirtue(3)'",
            "kind": "quickfix",
            "diagnostics": [diagnostic],
            "isPreferred": True,
            "edit": edit,
        }
    ]
    # Only quick fixes are offered, and only for the version they were computed for.
    assert _request(connection, uri, [diagnostic], only=["refactor"]) == []
    connection.change(uri, FIXED, 2)
    assert _request(connection, uri, [diagnostic]) == []
