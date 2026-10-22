"""Editor support for compile-time constants: completion, hover, definition, symbols."""

from __future__ import annotations

from lsprotocol.types import CompletionItemKind, SymbolKind

from aa2modulus.context.operation import SourceContext
from aa2modulus.lsp.completion.dispatch import completions
from aa2modulus.lsp.features.navigation import definition, document_symbols, hover
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.lsp.workspace.documents import SourceWorkspace
from tests.support.lsp_workspace import analyze_workspace, apply_text_edit

_SOURCE = """const Top: int = 9;
const TopS: string = "s";
macro say { Notification(TopS); }
module "M" {
  const Limit: int = 5;
  const "With Spaces": string = "a \\"b\\"";
  const Alias: int = Limit;
  const Pi: float = float_bits(0x7fc00001);
  global g: int = Limit;
  trigger "T" {
    on CARD_ADDED;
    let a: int = Limit;
    let b: int = const("Limit");
    let c: string = const("With Spaces");
    let d: int = Top;
    let e: float = Pi;
  }
}
"""


def _snapshot(source, context, uri="untitled:Constants"):
    workspace = SourceWorkspace()
    workspace.open(uri, source, 1)
    return workspace, analyze_workspace(workspace, uri, context)


def _at(source, text, member=None, nth=0):
    index = -1
    for _ in range(nth + 1):
        index = source.index(text, index + 1)
    return PositionCodec(source).position(index + (text.index(member) if member else 0))


def test_hover_on_every_reference_form_and_declaration(context):
    _, snapshot = _snapshot(_SOURCE, context)
    cases = [
        (_at(_SOURCE, "global g: int = Limit", "Limit"), "const Limit: int = 5"),
        (_at(_SOURCE, "let a: int = Limit", "Limit"), "const Limit: int = 5"),
        (_at(_SOURCE, 'const("Limit")', "Limit"), "const Limit: int = 5"),
        (_at(_SOURCE, "const Alias: int = Limit", "Alias"), "const Alias: int = 5"),
        (_at(_SOURCE, "const Alias: int = Limit", "Limit"), "const Limit: int = 5"),
        (_at(_SOURCE, "let d: int = Top", "Top"), "const Top: int = 9"),
        (_at(_SOURCE, "const Limit: int", "Limit"), "const Limit: int = 5"),
        (_at(_SOURCE, 'const("With Spaces")', "With"), 'const "With Spaces": string = "a \\"b\\""'),
        (_at(_SOURCE, 'const "With Spaces"', "With"), 'const "With Spaces": string = "a \\"b\\""'),
        (_at(_SOURCE, "let e: float = Pi", "Pi"), "const Pi: float = float_bits(0x7fc00001)"),
    ]
    for position, expected in cases:
        result = hover(snapshot, position, "utf-16")
        assert result is not None, (position, expected)
        assert expected in result.contents.value, (position, result.contents.value)


def test_definition_from_every_reference_form(context):
    workspace, snapshot = _snapshot(_SOURCE, context)

    def target(position):
        (location,) = definition(snapshot, position, "utf-16", workspace)
        return location.range

    declared = {
        "Limit": _at(_SOURCE, "const Limit", "Limit"),
        "Spaced": _at(_SOURCE, 'const "With Spaces"', '"With'),
        "Top": _at(_SOURCE, "const Top:", "Top"),
        "TopS": _at(_SOURCE, "const TopS", "TopS"),
    }
    uses = [
        (_at(_SOURCE, "let a: int = Limit", "Limit"), "Limit"),
        (_at(_SOURCE, 'const("Limit")', "Limit"), "Limit"),
        (_at(_SOURCE, "global g: int = Limit", "Limit"), "Limit"),
        (_at(_SOURCE, "const Alias: int = Limit", "Limit"), "Limit"),
        (_at(_SOURCE, "let d: int = Top", "Top"), "Top"),
        (_at(_SOURCE, "Notification(TopS)", "TopS"), "TopS"),
    ]
    for position, name in uses:
        assert target(position).start.line == declared[name].line, position
    spaced = target(_at(_SOURCE, 'const("With Spaces")', "With"))
    assert spaced.start.line == declared["Spaced"].line


def test_document_symbols_list_constants(context):
    _, snapshot = _snapshot(_SOURCE, context)
    symbols = document_symbols(snapshot, "utf-16")
    top = next(item for item in symbols if item.name == "Top")
    assert top.kind == SymbolKind.Constant
    module = next(item for item in symbols if item.name == "M")
    constants = {item.name: item for item in module.children if item.kind == SymbolKind.Constant}
    assert set(constants) == {"Limit", "With Spaces", "Alias", "Pi"}
    assert constants["Limit"].detail == "const Limit: int = 5"
    assert any(item.name == "g" and item.kind == SymbolKind.Variable for item in module.children)


def _labels(items):
    return {item.label: item for item in items}


def test_bare_completion_scopes_and_filters_by_type(context):
    head = _SOURCE.split("    let a:")[0]
    source = head + "    let x: int = "
    items = _labels(completions(source, len(source), context))
    assert items["Limit"].kind == CompletionItemKind.Constant
    assert items["Limit"].detail == "const Limit: int = 5"
    assert items["Top"].kind == CompletionItemKind.Constant
    assert items["Alias"].detail == "const Alias: int = 5"
    # Type filtering: string and float constants do not fit an int slot.
    assert "With Spaces" not in items
    assert "Pi" not in items

    source = head + "    let x: string = "
    spaced = _labels(completions(source, len(source), context))["With Spaces"]
    assert spaced.text_edit.new_text == 'const("With Spaces")'
    assert apply_text_edit(source, spaced).endswith('let x: string = const("With Spaces")')
    assert "Limit" not in _labels(completions(source, len(source), context))


def test_macro_body_sees_only_top_level_constants(context):
    full = _SOURCE.replace("Notification(TopS);", "Notification(")
    cursor = full.index("Notification(") + len("Notification(")
    names = _labels(completions(full, cursor, context))
    assert "TopS" in names and "Limit" not in names and "Alias" not in names


def test_const_string_completion_offers_every_name(context):
    head = _SOURCE.split("    let a:")[0]
    source = head + '    let x: int = const("'
    items = _labels(completions(source, len(source), context))
    assert {"Limit", "With Spaces", "Alias", "Pi", "Top"} <= set(items)
    assert all(item.kind == CompletionItemKind.Constant for item in items.values())
    assert apply_text_edit(source, items["Limit"]).endswith('const("Limit')
    assert apply_text_edit(source, items["With Spaces"]).endswith('const("With Spaces')

    source = head + '    let x: int = const("Li'
    assert set(_labels(completions(source, len(source), context))) == {"Limit"}

    # An existing closing quote is replaced together with the typed text.
    source = head + '    let x: int = const("Wi");'
    cursor = source.rindex('"Wi') + 3
    (item,) = completions(source, cursor, context)
    assert apply_text_edit(source, item).endswith('const("With Spaces");')


def test_const_string_escaping_for_quoted_names(context):
    source = (
        'module "M" { const "a\\"b": int = 1; trigger "T" { on CARD_ADDED; let x: int = const("'
    )
    (item,) = completions(source, len(source), context)
    assert item.label == 'a"b'
    assert item.text_edit.new_text == 'a\\"b'


def test_no_constant_completion_in_other_strings_or_statements(context):
    head = _SOURCE.split("    let a:")[0]
    source = head + '    let x: string = "'
    assert not completions(source, len(source), context)
    source = head + '    let x: string = variable("'
    assert not any(
        item.kind == CompletionItemKind.Constant
        for item in completions(source, len(source), context)
    )
    source = head + "    "
    assert "Limit" not in _labels(completions(source, len(source), context))


def test_partial_and_erroneous_source_keeps_constants_navigable(context):
    broken = _SOURCE.replace("let a: int = Limit;", "let a: int = Limit +;")
    workspace, snapshot = _snapshot(broken, context, "untitled:Broken")
    result = hover(snapshot, _at(broken, "const Limit", "Limit"), "utf-16")
    assert result is not None and "const Limit: int = 5" in result.contents.value
    names = {item.name for item in document_symbols(snapshot, "utf-16")}
    assert {"Top", "M"} <= names
    source = broken.split("    let a:")[0] + "    let x: int = "
    assert "Limit" in _labels(completions(source, len(source), context))
    assert definition(snapshot, _at(broken, 'const("Limit")', "Limit"), "utf-16", workspace)


def test_imported_library_constant_completes_hovers_and_navigates(tmp_path):
    library = tmp_path / "library.aa2mi"
    root = tmp_path / "root.aa2m"
    library_source = 'const LibLimit: int = 42;\nconst LibName: string = "lib";\n'
    library.write_text(library_source, encoding="utf-8")
    context = SourceContext.create(filename=str(root), import_base=tmp_path)
    source = (
        'import "library.aa2mi";\n'
        "macro say { Notification(LibName); }\n"
        'module "M" { trigger "T" { on CARD_ADDED; let a: int = LibLimit; '
        'let b: int = const("LibLimit"); } }\n'
    )

    in_module = source.replace("LibLimit; let b", "; let b", 1)
    cursor = in_module.index("let a: int = ") + len("let a: int = ")
    items = _labels(completions(in_module, cursor, context))
    assert items["LibLimit"].kind == CompletionItemKind.Constant
    assert items["LibLimit"].detail == "const LibLimit: int = 42"

    in_macro = source.replace("Notification(LibName)", "Notification(")
    cursor = in_macro.index("Notification(") + len("Notification(")
    items = _labels(completions(in_macro, cursor, context))
    assert items["LibName"].detail == 'const LibName: string = "lib"'
    assert "LibLimit" not in items  # int constant does not fit a string slot

    in_string = source.replace('const("LibLimit")', 'const("Lib")')
    cursor = in_string.index('const("Lib') + len('const("Lib')
    assert set(_labels(completions(in_string, cursor, context))) == {"LibLimit", "LibName"}

    workspace = SourceWorkspace()
    workspace.open(root.as_uri(), source, 1)
    snapshot = analyze_workspace(workspace, root.as_uri(), SourceContext.create(filename=str(root)))
    codec = PositionCodec(source)
    for text, member in (("let a: int = LibLimit", "LibLimit"), ('const("LibLimit")', "LibLimit")):
        point = codec.position(source.index(text) + text.index(member))
        result = hover(snapshot, point, "utf-16")
        assert result is not None and "const LibLimit: int = 42" in result.contents.value
        (target,) = definition(snapshot, point, "utf-16", workspace)
        assert target.uri == library.as_uri()
        assert target.range.start.line == 0
        assert target.range.start.character == library_source.index("LibLimit")
        assert target.range.end.character == library_source.index("LibLimit") + len("LibLimit")
    macro_point = codec.position(source.index("Notification(LibName") + len("Notification("))
    (target,) = definition(snapshot, macro_point, "utf-16", workspace)
    assert target.uri == library.as_uri() and target.range.start.line == 1
