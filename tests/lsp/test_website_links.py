"""Diagnostic codes and language words link to their sections on the documentation website."""

from __future__ import annotations

import re
from pathlib import Path

from lsprotocol import types

from aa2modulus.lsp.documentation.keywords import LANGUAGE_PAGES
from aa2modulus.lsp.features.navigation import hover
from aa2modulus.lsp.protocol.positions import PositionCodec
from aa2modulus.syntax.lexicon import source_lexicon
from tests.support.lsp_workspace import open_document, published_diagnostics

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_WORD_GROUPS = (
    "keywords",
    "types",
    "conversions",
    "rawForms",
    "rawPayload",
    "literals",
    "attributes",
)


def test_diagnostic_code_links_to_its_row(context):
    source = 'module "M" { trigger "T" { on CARD_ADDED; x = 1; } }'
    workspace, _ = open_document(source, context)
    (diagnostic,) = published_diagnostics(workspace, "untitled:Document", context)
    assert diagnostic.code == "UNDEFINED_VARIABLE"
    assert diagnostic.code_description == types.CodeDescription(
        "https://modulus.aa2d.net/reference/diagnostics/#UNDEFINED_VARIABLE"
    )


def test_language_word_hover_links_to_its_section(context):
    source = 'module "M" { trigger "T" { on CARD_ADDED; } }'
    _, snapshot = open_document(source, context)
    codec = PositionCodec(source)
    info = hover(snapshot, codec.position(source.index("igger")), "utf-16")
    assert info == types.Hover(
        types.MarkupContent(
            types.MarkupKind.Markdown,
            "[View online documentation](https://modulus.aa2d.net/language/modules/#triggers)",
        ),
        range=types.Range(types.Position(0, 13), types.Position(0, 20)),
    )


def test_every_language_word_has_an_existing_section():
    lexicon = dict(source_lexicon().groups)
    words = {word for group in _WORD_GROUPS for word in lexicon[group]}
    assert set(LANGUAGE_PAGES) == words
    for path in set(LANGUAGE_PAGES.values()):
        page, _, anchor = path.partition("#")
        file = _DOCS / (page.rstrip("/") + ".md")
        if not file.exists():
            file = _DOCS / page / "index.md"
        assert file.exists(), path
        if anchor:
            assert anchor in _heading_anchors(file.read_text(encoding="utf-8")), path


def _heading_anchors(text: str) -> set[str]:
    """Python-Markdown's default ``toc`` slugs of the page's headings."""

    headings = re.findall(r"^#+ (.+)$", text, re.MULTILINE)
    return {
        re.sub(r"[-\s]+", "-", re.sub(r"[^\w\s-]", "", heading).strip().lower())
        for heading in headings
    }
