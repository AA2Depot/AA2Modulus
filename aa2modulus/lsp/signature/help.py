"""Signature help for the incomplete call around a cursor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from lark import Token
from lsprotocol import types

from ...context.limits import SourceLimitError
from ...context.operation import SourceContext
from ...language.documentation import builtin_description
from ...language.types import CARD, SourceType, member_parameter_types, source_type_name, wire_type
from ...model.display import type_name
from ...model.native import ExpressionMetadata
from ...pipeline.analysis import SourceAnalysis
from ...pipeline.authoring import SourceAuthoring
from ...syntax.ast import SourceUnit
from ...syntax.parser.errors import SourceParseError
from ...syntax.recovery import BOUNDARY_TOKENS
from ..completion.call_site import expected_type_at, matching_call, member_call_forms
from ..completion.scope import authoring_view, visible_declarations
from ..completion.tokens import build_prefix
from ..documentation.comments import declaration_documentation
from ..documentation.signatures import (
    is_property,
    member_documentation,
    member_signature,
    parameter_labels,
    returns_text,
)


def _declared_type_name(value: SourceType) -> str:
    return "card" if value is CARD else type_name(value, unknown_style="space")


def _signature(
    name: str,
    labels: tuple[str, ...],
    *,
    documentation: str = "",
) -> types.SignatureInformation:
    full_label = f"{name}({', '.join(labels)})"
    offsets: list[tuple[int, int]] = []
    cursor = len(name) + 1
    for label in labels:
        offsets.append((cursor, cursor + len(label)))
        cursor += len(label) + 2
    parameters = tuple(types.ParameterInformation(label=label) for label in offsets)
    return types.SignatureInformation(
        label=full_label,
        documentation=documentation or None,
        parameters=parameters,
    )


def _macro_signatures(
    name: str,
    units: tuple[SourceUnit, ...],
    context: SourceContext,
    texts: Mapping[str, str],
) -> list[types.SignatureInformation]:
    results: list[types.SignatureInformation] = []
    for unit in units:
        for macro in unit.macros:
            if macro.name.casefold() == name.casefold():
                results.append(
                    _signature(
                        macro.name,
                        tuple(
                            f"{parameter.name}: {_declared_type_name(parameter.type)}"
                            for parameter in macro.parameters
                        ),
                        documentation=declaration_documentation(macro, texts),
                    )
                )
    return results


def _member_signatures(
    tokens: tuple[Token, ...],
    opening: int,
    name: str,
    unit: SourceUnit | None,
    source: str,
    offset: int,
    context: SourceContext,
) -> list[types.SignatureInformation]:
    """Signatures of ``receiver.Member(`` showing only the explicit arguments."""

    visible = {
        item.name: wire_type(item.type)
        for item in visible_declarations(unit, source, min(max(offset, 0), len(source)), context)
    }
    result: list[types.SignatureInformation] = []
    for form in member_call_forms(tokens, opening, name, unit, visible, context):
        if is_property(form):
            continue
        label = member_signature(form, context.source_policy)
        cursor = len(form.name) + 1
        parameters = []
        for item, kind in zip(form.arguments, member_parameter_types(form)[1:], strict=True):
            text = f"{item.name}: {source_type_name(kind)}"
            parameters.append(types.ParameterInformation(label=(cursor, cursor + len(text))))
            cursor += len(text) + 2
        target = context.catalog.member_target(form)
        body = builtin_description(context.source_policy, target)
        result.append(
            types.SignatureInformation(
                label=label,
                documentation=member_documentation(
                    form, target, body, returns=returns_text(context.source_policy, target)
                ),
                parameters=parameters,
            )
        )
    return result


def signature_help(
    source: str,
    offset: int,
    context: SourceContext,
    *,
    analysis: SourceAnalysis | None = None,
    authoring: SourceAuthoring | None = None,
    texts: Mapping[str, str] | None = None,
) -> types.SignatureHelp | None:
    """Return signatures for the incomplete call containing ``offset``."""

    prefix = build_prefix(source, offset, context, analysis=analysis)
    if prefix is None:
        return None
    call = matching_call(prefix.tokens)
    if call is None:
        return None
    opening, name, active = call
    tokens = prefix.tokens
    view = authoring_view(source, context, analysis, authoring)
    if isinstance(view.failure, SourceLimitError) or (
        isinstance(view.failure, SourceParseError) and view.ast is None
    ):
        return None
    source_texts = texts if texts is not None else {context.filename: source}
    after_on = opening >= 2 and tokens[opening - 2].type == "ON"
    member_signatures = (
        []
        if after_on
        else _member_signatures(tokens, opening, name, view.unit, source, offset, context)
    )
    if member_signatures:
        return types.SignatureHelp(
            signatures=member_signatures, active_signature=0, active_parameter=active
        )
    before_call = tokens[: opening - 1]
    statement_context = bool(before_call and before_call[-1].type in BOUNDARY_TOKENS)
    units = (view.unit,) if view.unit is not None else ()
    signatures = _macro_signatures(name, units, context, source_texts) if statement_context else []
    if after_on:
        signatures.extend(_event_signatures(name, context))
    elif not after_on and statement_context and not signatures:
        signatures.extend(_action_signatures(name, context))
    elif not after_on and not statement_context:
        expected_return = expected_type_at(tokens[: opening - 1], view.unit, {}, context)
        signatures.extend(_expression_signatures(name, expected_return, context))
    if not signatures:
        return None
    return types.SignatureHelp(
        signatures=signatures,
        active_signature=0,
        active_parameter=active,
    )


def _event_signatures(name: str, context: SourceContext) -> list[types.SignatureInformation]:
    policy = context.source_policy
    return [
        _signature(
            name,
            parameter_labels(policy, entry, unknown_style="space"),
            documentation=builtin_description(policy, entry),
        )
        for entry in context.catalog.event_candidates(name)
    ]


def _action_signatures(name: str, context: SourceContext) -> list[types.SignatureInformation]:
    policy = context.source_policy
    signatures: list[types.SignatureInformation] = []
    for entry in context.catalog.action_candidates(name):
        if any(signature.label.startswith(f"{name}(") for signature in signatures):
            continue
        signatures.append(
            _signature(
                name,
                parameter_labels(policy, entry, unknown_style="space"),
                documentation=builtin_description(policy, entry),
            )
        )
    return signatures


def _expression_signatures(
    name: str, expected_return: int | None, context: SourceContext
) -> list[types.SignatureInformation]:
    policy = context.source_policy
    candidates = context.catalog.candidates("expression", name, result_type=expected_return)
    signatures: list[types.SignatureInformation] = []
    for target in candidates:
        expression_entry = cast(ExpressionMetadata, target.metadata)
        signatures.append(
            _signature(
                name,
                parameter_labels(policy, expression_entry, unknown_style="space"),
                documentation=builtin_description(policy, expression_entry),
            )
        )
    return signatures
