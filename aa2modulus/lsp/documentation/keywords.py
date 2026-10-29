"""Website links for language words: keywords, types, raw-form words, literals and ``@allow``."""

from __future__ import annotations

from lsprotocol import types

from ...language.documentation import DOCS_WEBSITE
from ...syntax.scanner import scan_lexical
from ..protocol.positions import PositionCodec

_MODULES = "language/modules/"
_GLOBALS = "language/modules/#globals"
_IF = "language/control-flow/#if-and-else"
_BRANCHES = "language/control-flow/#standalone-branches"
_LOOP = "language/control-flow/#loop"
_FOR = "language/control-flow/#for"
_TEMPLATES = "language/libraries/#trigger-templates"
_TYPES = "language/#types"
_LITERALS = "language/#literals"
_RAW_FORMS = "language/raw-forms/"

# Each word's section below the website root. A test keeps the words in step
# with the lexicon and the sections with the headings under docs/.
LANGUAGE_PAGES: dict[str, str] = {
    "module": _MODULES,
    "description": "language/modules/#description",
    "depends_on": "language/modules/#dependencies",
    "global": _GLOBALS,
    "default": _GLOBALS,
    "current": _GLOBALS,
    "initialized": _GLOBALS,
    "trigger": "language/modules/#triggers",
    "on": "language/modules/#events",
    "let": "language/modules/#local-variables",
    "const": "language/constants/",
    "variable": "language/#names",
    "if": _IF,
    "else": _IF,
    "ElseIf": _BRANCHES,
    "Else": _BRANCHES,
    "loop": _LOOP,
    "break": _LOOP,
    "continue": _LOOP,
    "for": _FOR,
    "from": _FOR,
    "to": _FOR,
    "macro": "language/macros/",
    "param": "language/macros/#parameters",
    "import": "language/libraries/#imports",
    "import.trigger": _TEMPLATES,
    "slot": _TEMPLATES,
    "int": _TYPES,
    "float": _TYPES,
    "bool": _TYPES,
    "string": _TYPES,
    "card": _TYPES,
    "Card": _TYPES,
    "true": _LITERALS,
    "false": _LITERALS,
    "float_bits": "language/raw-forms/#exact-float-values",
    "raw_action": _RAW_FORMS,
    "raw_event": _RAW_FORMS,
    "raw_expression": _RAW_FORMS,
    "parameters": _RAW_FORMS,
    "constant": _RAW_FORMS,
    "named_constant": _RAW_FORMS,
    "type": _RAW_FORMS,
    "invalid": _RAW_FORMS,
    "@allow": "language/hazards/#acknowledging-a-bug-with-allow",
}
_WORD_CATEGORIES = frozenset({"keyword", "type", "attribute"})


def language_word_hover(codec: PositionCodec, position: types.Position) -> types.Hover | None:
    """A link to the website section of the language word at ``position``."""

    offset = codec.offset(position)
    for token in scan_lexical(codec.text):
        if token.start > offset:
            return None
        path = LANGUAGE_PAGES.get(codec.text[token.start : token.end])
        if offset < token.end and path is not None and token.category in _WORD_CATEGORIES:
            return types.Hover(
                types.MarkupContent(
                    types.MarkupKind.Markdown,
                    f"[View online documentation]({DOCS_WEBSITE}{path})",
                ),
                range=types.Range(codec.position(token.start), codec.position(token.end)),
            )
    return None
