"""Built-in pages by stable anchor, policy prose, and authored comment documentation."""

from __future__ import annotations

import dataclasses

import pytest

from aa2modulus.language.documentation import builtin_description
from aa2modulus.lsp.documentation.builtins import BuiltinDocumentation
from aa2modulus.lsp.documentation.comments import declaration_documentation
from aa2modulus.lsp.documentation.signatures import metadata_signature
from aa2modulus.lsp.features.navigation import definition, hover
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.signature.help import signature_help
from aa2modulus.lsp.workspace.documents import SourceWorkspace
from aa2modulus.metadata.identities import WireIdentity
from aa2modulus.syntax.parser.units import parse_source_unit
from tests.support.lsp_workspace import analyze_workspace


def test_builtin_definition_is_a_server_page_only_when_enabled(context):
    documentation = BuiltinDocumentation(context.metadata, enabled=True)
    workspace = SourceWorkspace()
    uri = "untitled:Module"
    source = 'module "M" { trigger "T" { Notification("hello"); } }'
    workspace.open(uri, source, 1)
    snapshot = analyze_workspace(workspace, uri, context)
    position = PositionCodec(source).position(source.index("Notification"))
    result = hover(snapshot, position, "utf-16")
    assert context.metadata.action(108).description in result.contents.value
    assert "Notification(text: string, isImportant: bool = false)" in result.contents.value
    (target,) = definition(snapshot, position, "utf-16", workspace, documentation=documentation)
    assert target.uri == "aa2m-builtin:/action-108.md"
    assert target.range.start == target.range.end
    assert (target.range.start.line, target.range.start.character) == (0, 0)

    documentation.enabled = False
    assert definition(snapshot, position, "utf-16", workspace, documentation=documentation) == []


def test_anchors_cover_actions_events_and_named_constant_ordinals(metadata):
    documentation = BuiltinDocumentation(metadata, enabled=True)
    assert documentation.anchor(metadata.action(108)) == "action-108"
    assert documentation.anchor(metadata.event(6)) == "event-6"
    first_int = next(item for item in metadata.named_constants if item.value_type == 1)
    assert documentation.anchor(first_int) == "named-constant-int-1"
    assert documentation.location(metadata.event(6)).uri == "aa2m-builtin:/event-6.md"


def test_policy_description_override_replaces_native_prose(context):
    policy = context.source_policy
    notification = context.metadata.action(108)
    assert builtin_description(policy, notification) == notification.description
    curated = dataclasses.replace(
        policy, description_overrides=((WireIdentity("action", 108), "Curated prose."),)
    )
    assert builtin_description(curated, notification) == "Curated prose."
    assert builtin_description(curated, context.metadata.action(63)) == (
        context.metadata.action(63).description
    )


def test_flat_signatures_name_parameters_from_policy(context):
    policy = context.source_policy
    start = context.metadata.action(51)
    assert metadata_signature("H.Start", start, policy) == "H.Start(pc: card, partner: card)"
    random = context.metadata.expression(1, 4)
    assert metadata_signature("Math.RandomInt", random, policy) == (
        "Math.RandomInt(min: int, max: int) -> int"
    )
    unnamed = dataclasses.replace(policy, parameter_name_entries=(), parameter_role_entries=())
    assert metadata_signature("H.Start", start, unnamed) == "H.Start(int, int)"


def test_signature_help_names_builtin_and_macro_parameters(context):
    source = 'module "M" { trigger "T" { H.Start('
    help_ = signature_help(source, len(source), context)
    assert help_ is not None
    assert help_.signatures[0].label == "H.Start(pc: card, partner: card)"
    assert help_.signatures[0].parameters[1].label == (
        len("H.Start(pc: card, "),
        len("H.Start(pc: card, partner: card"),
    )

    source = (
        'macro Tell { param message string; Notification(message); } module "M" { trigger "T" { '
        "Tell("
    )
    help_ = signature_help(source, len(source), context)
    assert help_ is not None
    assert help_.signatures[0].label == "Tell(message: string)"


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("// A description.\n// Second line.\n", "A description.\nSecond line."),
        ("/**\n * **Important.**\n *\n * More detail.\n */\n", "**Important.**\n\nMore detail."),
        ("/* Short description. */ ", "Short description."),
        ("// Not adjacent.\n\n", ""),
        ("macro Other {} // Trailing comment.\n", ""),
        ('macro Other { Notification("// not a comment"); }\n', ""),
    ],
)
def test_declaration_comments_are_adjacent_and_ignore_strings(prefix, expected):
    source = prefix + 'macro Documented { param amount int; } module "M" {}'
    unit = parse_source_unit(source, filename="comments.aa2m")
    macro = next(item for item in unit.macros if item.name == "Documented")
    assert declaration_documentation(macro, {"comments.aa2m": source}) == expected


def test_imported_comments_and_navigation_survive_unrelated_incomplete_edit(tmp_path, context):
    root = tmp_path / "root.aa2m"
    library = tmp_path / "library.aa2mi"
    library_source = (
        "// Tell the player.\nmacro Tell { param message string; Notification(message); }\n"
    )
    library.write_text(library_source, encoding="utf-8")
    workspace = SourceWorkspace()
    source = 'import "library.aa2mi"; module "M" { trigger "T" { Tell("x"); Noti'
    workspace.open(root.as_uri(), source, 1)
    workspace.open(
        library.as_uri(),
        library_source.replace("Tell the player.", "Edited buffer docs."),
        2,
        "aa2mi",
    )
    snapshot = analyze_workspace(workspace, root.as_uri(), context)
    point = PositionCodec(source).position(source.index('Tell("x")'))
    result = hover(snapshot, point, "utf-16")
    assert "Edited buffer docs." in result.contents.value
    target = definition(snapshot, point, "utf-16", workspace)[0]
    assert target.uri == library.as_uri()
    assert target.range.start.line == 1
    assert "Tell" in result.contents.value


def test_builtin_with_wrong_arguments_still_identifies_selected_page(context):
    documentation = BuiltinDocumentation(context.metadata, enabled=True)
    workspace = SourceWorkspace()
    uri = "untitled:Module"
    source = 'module "M" { trigger "T" { Notification(1); } }'
    workspace.open(uri, source, 1)
    snapshot = analyze_workspace(workspace, uri, context)
    point = PositionCodec(source).position(source.index("Notification"))
    assert "Notification(text: string" in hover(snapshot, point, "utf-16").contents.value
    (target,) = definition(snapshot, point, "utf-16", workspace, documentation=documentation)
    assert target.uri == "aa2m-builtin:/action-108.md"
