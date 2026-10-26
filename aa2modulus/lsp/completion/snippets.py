"""Keyword snippets, the empty-document starters and the source-kind keyword filter.

A snippet is offered only where the grammar accepts its keyword; its ``when``
condition picks the variant. To add or change one, edit ``_SNIPPETS`` and the
position table in ``tests/lsp/test_completion_snippets.py``, which checks that
every offered snippet parses where it is offered.
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from lark import Token
from lsprotocol import types

from ...syntax.ast import SourceUnit
from .request import CompletionRequest, CompletionSite
from .tokens import Prefix, contextual_tokens, literal_keywords

_INDENT = re.compile(r"^(?:    )+", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class _Position:
    """What the snippet conditions read about the cursor."""

    prefix: Prefix
    keywords: frozenset[str]
    # Keyword type of the top-level item around the cursor; ``None`` at the top level.
    enclosing: str | None


@dataclass(frozen=True, slots=True)
class _Snippet:
    keyword: str
    description: str
    body: str
    label: str = ""
    when: Callable[[_Position], bool] | None = None

    def __post_init__(self) -> None:
        # Bodies are written as indented blocks; the client converts tabs to its indentation.
        body = textwrap.dedent(self.body).strip("\n")
        body = _INDENT.sub(lambda match: "\t" * (len(match.group()) // 4), body)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "label", self.label or self.keyword)


def _top_level(position: _Position) -> bool:
    return position.enclosing is None


def _nested(position: _Position) -> bool:
    return position.enclosing is not None


def _constant_declaration(position: _Position) -> bool:
    """Whether ``const`` here starts a declaration, not a ``const("...")`` reference."""

    prefix = position.prefix
    parsed = contextual_tokens(prefix.parser, (*prefix.tokens, Token("CONST", "const")))
    return parsed is not None and "LPAR" not in parsed[1]


def _template_body(position: _Position) -> bool:
    # Template slots precede the trigger items; instance bodies hold only bindings.
    return "on" in position.keywords


def _instance_body(position: _Position) -> bool:
    return not _template_body(position)


def _block_statement(position: _Position) -> bool:
    # ``break if`` and ``continue if`` take a condition, not a block.
    tokens = position.prefix.tokens
    return not (tokens and tokens[-1].type == "LOOP_KEYWORD")


def _trigger_body(position: _Position) -> bool:
    # Macros cannot write a for-loop target; ``let`` is accepted only directly
    # in a trigger body, where the counter can be declared.
    return position.enclosing != "MACRO" and "let" in position.keywords


def _nested_block(position: _Position) -> bool:
    return position.enclosing != "MACRO" and "let" not in position.keywords


_MODULE = _Snippet(
    "module",
    "module with a trigger",
    """
    module "${1:Module name}" {
        description "${2:What this module does}";

        trigger "${3:Trigger name}" {
            on ${4:CARD_ADDED};
            $0
        }
    }
    """,
)

_LIBRARY = _Snippet(
    "library",
    "macro and trigger template",
    """
    macro ${1:notify} {
        param ${2:message} string;
        Notification(${2:message});
    }

    trigger "${3:Template name}" {
        slot ${4:text} string;
        on ${5:CARD_ADDED};
        ${1:notify}(${4:text});$0
    }
    """,
)

# Offered in this order when several share a keyword.
_SNIPPETS = (
    # Top level
    _MODULE,
    _Snippet("import", "library import", 'import "${1:library.aa2mi}";'),
    _Snippet(
        "macro",
        "statement macro with a parameter",
        """
        macro ${1:name} {
            param ${2:value} ${3|int,bool,float,string|};
            $0
        }
        """,
    ),
    _Snippet(
        "const",
        "compile-time constant",
        "const ${1:Name}: ${2|int,bool,float,string|} = ${3:0};",
        when=_constant_declaration,
    ),
    _Snippet(
        "trigger",
        "trigger template with a slot",
        """
        trigger "${1:Template name}" {
            slot ${2:name} ${3|int,bool,float,string|};
            on ${4:CARD_ADDED};
            $0
        }
        """,
        when=_top_level,
    ),
    # Module items
    _Snippet(
        "trigger",
        "trigger with an event",
        """
        trigger "${1:Trigger name}" {
            on ${2:CARD_ADDED};
            $0
        }
        """,
        when=_nested,
    ),
    _Snippet(
        "import.trigger",
        "trigger template instance",
        """
        import.trigger "${1:Template name}" "${2:Instance name}" {
            slot ${3:name} = ${4:0};
        }
        """,
    ),
    _Snippet("global", "module global", "global ${1:name}: ${2|int,bool,float,string|} = ${3:0};"),
    _Snippet("description", "module description", 'description "${1:What this module does}";'),
    _Snippet("depends_on", "module dependency", 'depends_on "${1:Module name}";'),
    # Template, instance, macro and trigger items
    _Snippet(
        "slot",
        "template slot",
        "slot ${1:name} ${2|int,bool,float,string|};",
        when=_template_body,
    ),
    _Snippet("slot", "slot value", "slot ${1:name} = ${2:0};", when=_instance_body),
    _Snippet("param", "macro parameter", "param ${1:name} ${2|int,bool,float,string|};"),
    _Snippet("on", "event", "on ${1:CARD_ADDED};"),
    _Snippet("let", "trigger local", "let ${1:name}: ${2|int,bool,float,string|} = ${3:0};"),
    # Statements
    _Snippet(
        "if",
        "if block",
        """
        if ${1:condition} {
            $0
        }
        """,
        when=_block_statement,
    ),
    _Snippet(
        "if",
        "if and else blocks",
        """
        if ${1:condition} {
            $2
        } else {
            $0
        }
        """,
        when=_block_statement,
    ),
    _Snippet(
        "else",
        "else block",
        """
        else {
            $0
        }
        """,
    ),
    _Snippet(
        "else",
        "else if block",
        """
        else if ${1:condition} {
            $0
        }
        """,
        label="else if",
    ),
    _Snippet(
        "loop",
        "loop block",
        """
        loop {
            $0
        }
        """,
    ),
    _Snippet(
        "for",
        "counted loop with its local",
        """
        let ${1:i}: int = 0;
        for ${1:i} from ${2:0} to ${3:3} {
            $0
        }
        """,
        when=_trigger_body,
    ),
    _Snippet(
        "for",
        "counted loop",
        """
        for ${1:i} from ${2:0} to ${3:3} {
            $0
        }
        """,
        when=_nested_block,
    ),
)


def unavailable_keywords(
    request: CompletionRequest, site: CompletionSite, unit: SourceUnit | None
) -> frozenset[str]:
    """Keywords the grammar accepts here but the file's source kind does not.

    A library has no module; a module file has one module and no trigger templates.
    """

    if request.source_kind == "library":
        return frozenset({"module"})
    if _enclosing(site.prefix.tokens) is not None:
        return frozenset()
    if unit is not None and unit.module is not None:
        return frozenset({"module", "trigger"})
    return frozenset({"trigger"})


def snippet_items(
    request: CompletionRequest, site: CompletionSite, excluded: Collection[str]
) -> list[types.CompletionItem]:
    """Snippets for the accepted keywords, plus the file starter in an empty document."""

    prefix = site.prefix
    keywords = literal_keywords(prefix.parser, prefix.expected)
    position = _Position(prefix, frozenset(keywords), _enclosing(prefix.tokens))
    # Only the typed word is replaced: nothing before or after it.
    empty = not prefix.tokens and site.following is None
    starter = (_LIBRARY if request.source_kind == "library" else _MODULE) if empty else None
    items: list[types.CompletionItem] = []
    if starter is _LIBRARY and _matches(_LIBRARY.label, prefix):
        items.append(_item(_LIBRARY, site, "0"))
    for keyword in keywords:
        if keyword in excluded or not _matches(keyword, prefix):
            continue
        offered = (
            snippet
            for snippet in _SNIPPETS
            if snippet.keyword == keyword and (snippet.when is None or snippet.when(position))
        )
        for index, snippet in enumerate(offered):
            items.append(_item(snippet, site, "0" if snippet is starter else f"1{keyword} {index}"))
    return items


def _enclosing(tokens: Sequence[Token]) -> str | None:
    """Keyword type of the top-level item around the cursor; ``None`` at the top level."""

    depth = 0
    keyword = None
    opener = None
    for token in tokens:
        if token.type == "LBRACE":
            if depth == 0:
                opener = keyword
            depth += 1
        elif token.type == "RBRACE" and depth:
            depth -= 1
        elif depth == 0 and token.type in {"MODULE", "MACRO", "TRIGGER"}:
            keyword = token.type
    return opener if depth else None


def _matches(label: str, prefix: Prefix) -> bool:
    return not prefix.suffix or label.casefold().startswith(prefix.suffix.casefold())


def _item(snippet: _Snippet, site: CompletionSite, sort_text: str) -> types.CompletionItem:
    return types.CompletionItem(
        label=snippet.label,
        label_details=types.CompletionItemLabelDetails(description=snippet.description),
        kind=types.CompletionItemKind.Snippet,
        detail=snippet.description,
        filter_text=snippet.label,
        sort_text=sort_text,
        text_edit=types.TextEdit(site.edit_range, snippet.body),
        insert_text_format=types.InsertTextFormat.Snippet,
    )
