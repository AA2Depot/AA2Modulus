"""Completion items for built-ins, authored declarations, constants and attributes."""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence

from lark import Token
from lsprotocol import types

from ...context.operation import SourceContext
from ...core.source_names import is_source_name
from ...language.catalog.model import NativeTarget, SourceForm
from ...language.documentation import builtin_description
from ...language.types import CARD, CARD_ROLE, wire_type
from ...language.values import SourceValue
from ...model.display import value_text
from ...model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ...model.types import ValueType
from ...model.values import Value
from ...pipeline.authoring import SourceAuthoring
from ...syntax.ast import (
    SourceConstant,
    SourceGlobal,
    SourceLocal,
    SourceMacro,
    SourceParameter,
    SourceUnit,
)
from ..documentation.comments import declaration_documentation
from ..documentation.signatures import (
    constant_signature,
    declaration_signature,
    metadata_signature,
    returns_text,
)
from .request import CompletionRequest, CompletionSite
from .scope import constant_values, visible_declarations
from .tokens import Prefix, lex_tokens, literal_keywords


def _call_text(
    name: str,
    parameters: tuple[int, ...],
    *,
    context: SourceContext,
    action: ActionMetadata | None = None,
    statement: bool = False,
    event: bool = False,
    snippet_support: bool = False,
    existing_parentheses: bool = False,
    existing_statement_suffix: bool = False,
) -> str:
    if event and not parameters:
        suffix = "" if existing_statement_suffix or existing_parentheses else ";"
        return f"{name}{suffix}"
    if not snippet_support or existing_parentheses:
        return name
    if not parameters and not statement:
        return name
    required = len(parameters)
    if action is not None:
        while (
            required and context.source_policy.action_default(action.id, required - 1) is not None
        ):
            required -= 1
    defaults = {
        ValueType.INT: "0",
        ValueType.BOOL: "false",
        ValueType.FLOAT: "0.0",
        ValueType.STRING: '""',
        ValueType.INVALID: "variable",
    }
    placeholders = []
    for index, parameter in enumerate(parameters[:required], 1):
        default = context.source_policy.action_default(action.id, index - 1) if action else None
        value = (
            value_text(default.value)
            if default is not None
            else defaults.get(ValueType(parameter), "0")
        )
        placeholders.append(f"${{{index}:{value}}}")
    suffix = ";" if statement and not existing_statement_suffix else ""
    return f"{name}({', '.join(placeholders)}){suffix}$0"


def _variable_text(name: str, context: SourceContext) -> str:
    return (
        name
        if is_source_name(name, allow_qualified=False)
        and name.casefold() not in context.catalog.protected_names
        else f"variable({value_text(Value.string(name))})"
    )


def _constant_text(name: str) -> str:
    return name if is_source_name(name, allow_qualified=False) else _const_call(name)


def _const_call(name: str) -> str:
    return f"const({value_text(Value.string(name))})"


CONST_STRING = re.compile(r'\bconst\s*\(\s*"((?:[^"\\\r\n]|\\.)*)\Z')


def constant_string_completions(
    request: CompletionRequest, view: SourceAuthoring
) -> list[types.CompletionItem] | None:
    """Complete constant names inside ``const("...")``; None when not in that context."""

    source, offset, context = request.source, request.offset, request.context
    match = CONST_STRING.search(source[:offset])
    if match is None:
        return None
    quote = match.start(1) - 1
    tokens = lex_tokens(source, quote, context)
    if tokens is None or len(tokens) < 2 or tokens[-1].type != "LPAR" or tokens[-2].type != "CONST":
        return None
    try:
        typed = json.loads(f'"{match.group(1)}"')
    except ValueError:
        typed = match.group(1)
    visible = visible_declarations(view.unit, source, offset, context)
    values = constant_values(view.unit, context)
    # Replace the typed text plus the rest of the string up to its closing quote.
    end = offset
    while end < len(source) and source[end] not in '"\r\n':
        end += 2 if source[end] == "\\" else 1
    end = min(end, len(source))
    codec = request.codec
    source_texts = request.source_texts
    results: list[types.CompletionItem] = []
    for declaration in visible:
        if not isinstance(declaration, SourceConstant) or not declaration.name.startswith(typed):
            continue
        escaped = json.dumps(declaration.name, ensure_ascii=True)[1:-1]
        documentation = declaration_documentation(declaration, source_texts)
        results.append(
            types.CompletionItem(
                label=declaration.name,
                kind=types.CompletionItemKind.Constant,
                detail=constant_signature(declaration, values.get(id(declaration))),
                filter_text=declaration.name,
                documentation=types.MarkupContent(types.MarkupKind.Markdown, documentation)
                if documentation
                else None,
                text_edit=types.TextEdit(
                    types.Range(codec.position(quote + 1), codec.position(end)), escaped
                ),
            )
        )
    return results


def keyword_items(site: CompletionSite, excluded: Collection[str]) -> list[types.CompletionItem]:
    """Grammar keywords accepted at the cursor that match the typed prefix, except ``excluded``."""

    prefix = site.prefix
    results: list[types.CompletionItem] = []
    for keyword in literal_keywords(prefix.parser, prefix.expected):
        if keyword in excluded:
            continue
        if keyword in {"true", "false"} and site.expected_type not in {None, ValueType.BOOL}:
            continue
        if prefix.suffix and not keyword.casefold().startswith(prefix.suffix.casefold()):
            continue
        results.append(
            types.CompletionItem(
                label=keyword,
                kind=types.CompletionItemKind.Keyword,
                filter_text=keyword,
                text_edit=types.TextEdit(site.edit_range, keyword),
            )
        )
    return results


def builtin_items(request: CompletionRequest, site: CompletionSite) -> list[types.CompletionItem]:
    """Built-in actions, events, expressions and constants, then source values."""

    if not site.expression_position and not site.statement_position:
        return []
    items = _group_items(request, site)
    items.extend(_source_value_items(request, site))
    return items


# Native target kinds in completion order.
_GROUP_KINDS = ("action", "event", "expression", "named_constant")


def _kind_enabled(kind: str, site: CompletionSite) -> bool:
    if kind == "action" and (not site.statement_position or site.event_position):
        return False
    if kind == "event" and not site.event_position:
        return False
    if site.event_position and kind != "event":
        return False
    if kind == "named_constant" and not site.expression_position:
        return False
    if kind == "expression" and not (site.expression_position or site.statement_position):
        # Statement positions keep only card receivers (see _group_items).
        return False
    return not (kind == "named_constant" and site.existing_parentheses)


def _entry_selected(entry: object, expected_type: int | None) -> bool:
    """Whether a target's metadata is a flat built-in compatible with the expected type."""

    if isinstance(entry, SourceValue):
        return False
    if isinstance(entry, ExpressionMetadata) and (
        expected_type is not None and entry.return_type != expected_type
    ):
        return False
    return not (
        isinstance(entry, NamedConstantMetadata)
        and expected_type is not None
        and entry.value_type != expected_type
    )


def _group_items(request: CompletionRequest, site: CompletionSite) -> list[types.CompletionItem]:
    """Items of the registered native targets, one per reversible flat form."""

    items: list[types.CompletionItem] = []
    for kind in _GROUP_KINDS:
        if not _kind_enabled(kind, site):
            continue
        for target in request.context.catalog.native_targets.values():
            if target.wire.kind != kind:
                continue
            entry = target.metadata
            receiver = _returns_card(request, entry)
            if not _entry_selected(entry, site.expected_type) and (
                not receiver or site.existing_parentheses
            ):
                continue
            if kind == "expression" and site.statement_position and not receiver:
                continue
            for form in target.forms:
                if form.kind == "member" or not form.reversible:
                    # Card-first targets are members, never flat names.
                    continue
                item = _form_item(request, site, kind, target, form)
                if item is not None:
                    items.append(item)
    return items


def _returns_card(request: CompletionRequest, entry: object) -> bool:
    """Whether a built-in expression returns a card, a receiver for member statements and values.

    Card members return every value type, so a receiver fits any value slot.
    """

    return (
        isinstance(entry, ExpressionMetadata)
        and request.context.source_policy.expression_result_role(entry.return_type, entry.id)
        == CARD_ROLE
    )


def _form_item(
    request: CompletionRequest,
    site: CompletionSite,
    kind: str,
    target: NativeTarget,
    form: SourceForm,
) -> types.CompletionItem | None:
    context = request.context
    catalog = context.catalog
    policy = context.source_policy
    entry = target.metadata
    prefix = site.prefix
    name = form.spelling
    selected = catalog.candidates(
        target.wire.kind,
        name,
        result_type=target.signature.result_type,
        parameter_types=target.signature.parameter_types,
    )
    if not any(candidate.wire == target.wire for candidate in selected):
        return None
    if prefix.suffix and not name.casefold().startswith(prefix.suffix.casefold()):
        return None
    if isinstance(entry, NamedConstantMetadata) and name in site.visible:
        return None
    body = builtin_description(policy, entry)
    if returns := returns_text(policy, entry):
        body = f"{returns}\n\n{body}" if body else returns
    insert = (
        name
        if isinstance(entry, NamedConstantMetadata)
        else _call_text(
            name,
            entry.parameter_types,
            context=context,
            action=entry if isinstance(entry, ActionMetadata) else None,
            # A card receiver is continued with a member, never terminated.
            statement=kind != "expression" and (site.statement_position or site.event_position),
            event=site.event_position,
            snippet_support=request.snippet_support,
            existing_parentheses=site.existing_parentheses,
            existing_statement_suffix=site.existing_statement_suffix,
        )
    )
    if (
        form.kind == "getter"
        and not site.existing_parentheses
        and name in site.visible
        and name.casefold() not in catalog.protected_names
        and is_source_name(name, allow_qualified=False)
    ):
        # An explicit call selects a built-in getter when a
        # same-named authored variable owns the bare spelling.
        insert = f"{name}()"
    return types.CompletionItem(
        label=name,
        kind=_item_kind(kind, entry),
        detail=metadata_signature(name, entry, policy),
        filter_text=name,
        # Values whose result role matches the argument rank first, and card
        # receivers that need a member to fit the slot rank last.
        sort_text=f"0{name}"
        if site.expected_role is not None
        and isinstance(entry, ExpressionMetadata)
        and policy.expression_result_role(entry.return_type, entry.id) == site.expected_role
        else f"2{name}"
        if site.expected_type is not None
        and isinstance(entry, ExpressionMetadata)
        and entry.return_type != site.expected_type
        else None,
        documentation=types.MarkupContent(types.MarkupKind.Markdown, body) if body else None,
        insert_text=insert,
        insert_text_format=types.InsertTextFormat.Snippet
        if request.snippet_support
        and not site.existing_parentheses
        and _takes_arguments(kind, entry)
        else types.InsertTextFormat.PlainText,
        command=None,
    )


def _item_kind(kind: str, entry: object) -> types.CompletionItemKind:
    if kind == "named_constant":
        return types.CompletionItemKind.Constant
    if kind == "event":
        return types.CompletionItemKind.Event
    if isinstance(entry, ExpressionMetadata) and not entry.parameter_types:
        return types.CompletionItemKind.Property
    return types.CompletionItemKind.Function


def _takes_arguments(kind: str, entry: object) -> bool:
    """Whether the built-in is spelled as a call whose arguments a snippet can fill."""

    return kind != "named_constant" and (
        kind == "action"
        or (isinstance(entry, (EventMetadata, ExpressionMetadata)) and bool(entry.parameter_types))
    )


def _source_value_items(
    request: CompletionRequest, site: CompletionSite
) -> list[types.CompletionItem]:
    policy = request.context.source_policy
    items: list[types.CompletionItem] = []
    for source_value in request.context.catalog.source_values:
        if site.existing_parentheses:
            continue
        if site.expected_type is not None and source_value.value_type != site.expected_type:
            continue
        name = source_value.name
        if site.prefix.suffix and not name.casefold().startswith(site.prefix.suffix.casefold()):
            continue
        if name in site.visible:
            continue
        body = builtin_description(policy, source_value)
        items.append(
            types.CompletionItem(
                label=name,
                kind=types.CompletionItemKind.Constant,
                detail=metadata_signature(name, source_value, policy),
                filter_text=name,
                documentation=types.MarkupContent(types.MarkupKind.Markdown, body)
                if body
                else None,
                insert_text=name,
                insert_text_format=types.InsertTextFormat.PlainText,
                command=None,
            )
        )
    return items


def authored_items(
    request: CompletionRequest,
    site: CompletionSite,
    declarations: Sequence[
        SourceGlobal | SourceLocal | SourceParameter | SourceConstant | SourceMacro
    ],
    unit: SourceUnit | None,
) -> list[types.CompletionItem]:
    """Authored variables, constants and macros that match the typed prefix."""

    context = request.context
    constant_by_declaration = (
        constant_values(unit, context)
        if any(isinstance(item, SourceConstant) for item in declarations)
        else {}
    )
    results: list[types.CompletionItem] = []
    macro_names: set[str] = set()
    for declaration in declarations:
        name = declaration.name
        if isinstance(declaration, SourceMacro):
            if name.casefold() in macro_names:
                continue
            macro_names.add(name.casefold())
        elif (
            site.expected_type is not None
            and wire_type(declaration.type) != site.expected_type
            # A card is a receiver whose members fit every value slot.
            and declaration.type is not CARD
        ):
            continue
        matches = (
            name.casefold().startswith(site.prefix.suffix.casefold())
            if isinstance(declaration, SourceMacro)
            else name.startswith(site.prefix.suffix)
        )
        if site.prefix.suffix and not matches:
            continue
        results.append(_authored_item(request, site, declaration, constant_by_declaration))
    return results


def _authored_item(
    request: CompletionRequest,
    site: CompletionSite,
    declaration: SourceGlobal | SourceLocal | SourceParameter | SourceConstant | SourceMacro,
    constant_by_declaration: Mapping[int, Value | None],
) -> types.CompletionItem:
    context = request.context
    name = declaration.name
    macro = isinstance(declaration, SourceMacro)
    documentation = declaration_documentation(declaration, request.source_texts)
    insert = (
        _call_text(
            name,
            tuple(wire_type(item.type) for item in declaration.parameters),
            context=context,
            statement=True,
            snippet_support=request.snippet_support,
            existing_parentheses=site.existing_parentheses,
            existing_statement_suffix=site.existing_statement_suffix,
        )
        if isinstance(declaration, SourceMacro)
        else f"{_variable_text(name, context)} = "
        if site.statement_position
        and isinstance(declaration, (SourceGlobal, SourceLocal))
        # A card variable usually starts a member statement, so it stays bare.
        and declaration.type is not CARD
        and not (site.following is not None and site.following.type == "EQUAL")
        else _constant_text(name)
        if isinstance(declaration, SourceConstant)
        else _variable_text(name, context)
    )
    kind = (
        types.CompletionItemKind.Function
        if macro
        else types.CompletionItemKind.Constant
        if isinstance(declaration, SourceConstant)
        else types.CompletionItemKind.Variable
    )
    return types.CompletionItem(
        label=name,
        kind=kind,
        detail=constant_signature(declaration, constant_by_declaration.get(id(declaration)))
        if isinstance(declaration, SourceConstant)
        else declaration_signature(declaration),
        filter_text=name,
        documentation=types.MarkupContent(types.MarkupKind.Markdown, documentation)
        if documentation
        else None,
        # Card variables rank first where a card is expected, and last where
        # they need a member to fit the slot.
        sort_text=f"0{name}"
        if site.expected_role == CARD_ROLE
        and not isinstance(declaration, SourceMacro)
        and declaration.type is CARD
        else f"2{name}"
        if site.expected_type is not None
        and not isinstance(declaration, SourceMacro)
        and wire_type(declaration.type) != site.expected_type
        else None,
        text_edit=types.TextEdit(site.edit_range, insert),
        insert_text_format=types.InsertTextFormat.Snippet
        if macro and request.snippet_support and not site.existing_parentheses
        else types.InsertTextFormat.PlainText,
        command=None,
    )


def allow_codes_listed(tokens: tuple[Token, ...]) -> tuple[str, ...] | None:
    """Codes before the cursor inside ``@allow(...)``, or ``None`` outside one."""

    position = len(tokens)
    listed: list[str] = []
    while (
        position >= 2
        and tokens[position - 1].type == "COMMA"
        and tokens[position - 2].type == "IDENT"
    ):
        listed.append(str(tokens[position - 2]))
        position -= 2
    if (
        position >= 2
        and tokens[position - 1].type == "LPAR"
        and tokens[position - 2].type == "_ALLOW"
    ):
        return tuple(listed)
    return None


def allow_completions(
    request: CompletionRequest, prefix: Prefix, listed: tuple[str, ...]
) -> list[types.CompletionItem]:
    """Policy-acknowledgeable codes not yet listed in this attribute."""

    codec = request.codec
    edit_range = types.Range(codec.position(prefix.start), codec.position(request.offset))
    return [
        types.CompletionItem(
            label=code,
            kind=types.CompletionItemKind.EnumMember,
            detail="acknowledgeable native hazard",
            filter_text=code,
            text_edit=types.TextEdit(edit_range, code),
        )
        for code in request.context.source_policy.acknowledgeable_codes
        if code not in listed and code.casefold().startswith(prefix.suffix.casefold())
    ]
