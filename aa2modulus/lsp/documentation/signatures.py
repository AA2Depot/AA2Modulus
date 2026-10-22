"""Signature and documentation text for built-ins and source declarations."""

from __future__ import annotations

import json

from ...core.source_names import is_source_name
from ...language.documentation import DocumentedMetadata, builtin_anchor
from ...language.policy import LanguagePolicy
from ...language.types import (
    CARD,
    member_parameter_types,
    parameter_types,
    result_type,
    role_type,
    source_type_name,
)
from ...language.values import MemberForm, SourceValue
from ...metadata.identities import NativeMetadata, native_key
from ...model.display import type_name, value_text
from ...model.native import ActionMetadata, ExpressionMetadata, NamedConstantMetadata
from ...model.types import TypeId, ValueType
from ...model.values import Value
from ...syntax import ast


def parameter_labels(
    policy: LanguagePolicy,
    metadata: NativeMetadata,
    *,
    unknown_style: str = "hash",
) -> tuple[str, ...]:
    """``name: type`` per native slot (``type`` when unnamed), with action defaults."""

    if isinstance(metadata, NamedConstantMetadata):
        return ()
    names = policy.parameter_names(native_key(metadata))
    kinds = (
        parameter_types(policy, metadata)
        if isinstance(metadata, (ActionMetadata, ExpressionMetadata))
        else metadata.parameter_types
    )
    labels: list[str] = []
    for index, parameter in enumerate(kinds):
        label = (
            source_type_name(parameter)
            if parameter is CARD
            else type_name(parameter, unknown_style=unknown_style)
        )
        if names is not None:
            label = f"{names[index]}: {label}"
        if isinstance(metadata, ActionMetadata):
            default = policy.action_default(metadata.id, index)
            if default is not None:
                label += f" = {value_text(default.value)}"
        labels.append(label)
    return tuple(labels)


def metadata_signature(name: str, metadata: DocumentedMetadata, policy: LanguagePolicy) -> str:
    if isinstance(metadata, SourceValue):
        return f"{name}: {type_name(metadata.value_type)} = {value_text(metadata.value)}"
    if isinstance(metadata, NamedConstantMetadata):
        result = f"{name}: {type_name(metadata.value_type)}"
        if metadata.value is not None:
            result += f" = {value_text(metadata.value)}"
        return result
    result = f"{name}({', '.join(parameter_labels(policy, metadata))})"
    if isinstance(metadata, ExpressionMetadata):
        result += f" -> {source_type_name(result_type(policy, metadata))}"
    return result


def returns_text(policy: LanguagePolicy, metadata: object) -> str:
    """``Returns: card`` when policy gives the expression result a role, else empty."""

    if not isinstance(metadata, ExpressionMetadata):
        return ""
    role = policy.expression_result_role(metadata.return_type, metadata.id)
    return "" if role is None else f"Returns: {_role_text(metadata.return_type, role)}"


def _role_text(kind: TypeId, role: str) -> str:
    """``card`` for a card-typed value, else the native type and its documentation role."""

    typed = role_type(kind, role)
    return "card" if typed is CARD else f"{type_name(kind)} ({role})"


def is_property(form: MemberForm) -> bool:
    """A zero-argument value member, written without parentheses."""

    return form.target.kind == "expression" and not form.arguments


def member_signature(form: MemberForm, policy: LanguagePolicy, *, receiver: bool = False) -> str:
    """Render the explicit receiver-call arguments; the receiver is not a parameter.

    With ``receiver`` the receiver role leads: ``<card>.SetVirtue(value: int)``.
    """

    prefix = f"<{form.receiver_role}>." if receiver else ""
    if is_property(form):
        result = f"{prefix}{form.name}"
    else:
        arguments = ", ".join(
            f"{item.name}: {source_type_name(kind)}"
            for item, kind in zip(form.arguments, member_parameter_types(form)[1:], strict=True)
        )
        result = f"{prefix}{form.name}({arguments})"
    if form.result_type is not None:
        role = policy.expression_result_role(form.result_type, form.target.identifier)
        result += f" -> {source_type_name(role_type(form.result_type, role))}"
    return result


def member_documentation(
    form: MemberForm,
    target: ActionMetadata | ExpressionMetadata,
    body: str = "",
    *,
    returns: str = "",
) -> str:
    """Describe receiver, argument and result roles, then the native target's documentation."""

    lines = [f"Receiver: {_role_text(form.receiver_type, form.receiver_role)}"]
    lines.extend(
        f"- `{item.name}`: {_role_text(kind, item.role)}"
        for item, kind in zip(form.arguments, form.argument_types, strict=True)
    )
    if returns:
        lines.append(returns)
    lines.append(f"Native target: {target.name} (`{builtin_anchor(target)}`)")
    text = "\n".join(lines)
    description = body or target.description
    return f"{text}\n\n{description}" if description else text


def constant_signature(node: ast.SourceConstant, value: Value | None = None) -> str:
    """``const Name: type = literal``; the resolved value wins over the authored link."""

    name = node.name if is_source_name(node.name, allow_qualified=False) else json.dumps(node.name)
    head = f"const {name}: {type_name(node.type)}"
    if value is not None:
        return f"{head} = {value_text(value)}"
    if isinstance(node.value, ast.SourceLiteral):
        return f"{head} = {_literal_text(node.value, node.type)}"
    if isinstance(node.value, ast.SourceName):
        return f"{head} = {node.value.name}"
    return f"{head} = const({json.dumps(node.value.name)})"


def _literal_text(literal: ast.SourceLiteral, kind: int) -> str:
    payload = literal.value
    if isinstance(payload, ast.FloatBitsLiteral):
        return f"float_bits(0x{payload.bits:08x})"
    try:
        return value_text(Value(ValueType(kind), payload))
    except (TypeError, ValueError):
        return str(payload)


def declaration_signature(node: object) -> str:
    if isinstance(node, ast.SourceConstant):
        return constant_signature(node)
    if isinstance(node, (ast.SourceGlobal, ast.SourceLocal, ast.SourceParameter)):
        return f"{node.name}: {source_type_name(node.type)}"
    if isinstance(node, ast.SourceMacro):
        parameters = ", ".join(
            f"{item.name}: {source_type_name(item.type)}" for item in node.parameters
        )
        return f"macro {node.name}({parameters})"
    if isinstance(node, ast.SourceTriggerTemplate):
        slots = ", ".join(f"{item.name}: {source_type_name(item.type)}" for item in node.slots)
        return f"trigger template {node.name}({slots})"
    if isinstance(node, (ast.SourceModule, ast.SourceTrigger)):
        return f"{'module' if isinstance(node, ast.SourceModule) else 'trigger'} {node.name!r}"
    return ""
