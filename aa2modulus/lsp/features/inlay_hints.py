"""Parameter-name inlay hints before literal call arguments.

Names come from the binder's selection for each call: a member form's
explicit argument names, the policy ``[parameter_names]`` of a flat built-in
(the chosen overload), or a macro's parameters. Unresolved calls, raw forms
and non-literal arguments get no hint, and a lone argument goes unlabeled
when its name is generic or already part of the callee name
(``coach.SetStyle(2)``). A string literal filling a storage key (member role
``key``, or a flat parameter named ``key``) names itself and is not labeled.
"""

from __future__ import annotations

from dataclasses import dataclass

from lsprotocol import types

from ...core.locations import SourceSpan
from ...hir.symbols import BoundReference
from ...metadata.identities import native_key
from ...model.native import ActionMetadata, ExpressionMetadata
from ...syntax import ast
from ...syntax.spans import qualified_segment_spans
from ...syntax.walk import walk_ast
from ..protocol.positions import position_codec
from ..workspace.documents import Snapshot
from .lookup import bound_references

_GENERIC_NAMES = frozenset({"value"})

type _Call = ast.SourceCall | ast.SourceAction | ast.SourceMemberCall | ast.SourceMemberAction


@dataclass(frozen=True, slots=True)
class _Hint:
    offset: int
    label: str


def _is_literal(node: object) -> bool:
    while isinstance(node, ast.SourceUnary):
        node = node.operand
    return isinstance(node, ast.SourceLiteral)


def _callee(node: _Call) -> tuple[str, SourceSpan | None]:
    """The written callee name and the span its binder reference records."""

    if isinstance(node, (ast.SourceMemberCall, ast.SourceMemberAction)):
        return node.member, node.name_span
    return node.name or "", node.name_span


def _parameters(snapshot: Snapshot, reference: BoundReference) -> tuple[tuple[str, bool], ...]:
    """``(name, is storage key)`` per explicit argument of the selected target."""

    if isinstance(reference.declaration, ast.SourceMacro):
        return tuple((item.name, False) for item in reference.declaration.parameters)
    if reference.member_form is not None:
        return tuple((item.name, item.role == "key") for item in reference.member_form.arguments)
    if isinstance(reference.metadata, (ActionMetadata, ExpressionMetadata)):
        policy = snapshot.analysis.context.source_policy
        names = policy.parameter_names(native_key(reference.metadata)) or ()
        return tuple((name, name == "key") for name in names)
    return ()


def collect_hints(snapshot: Snapshot) -> list[_Hint]:
    """Hints for the document's calls, ordered by offset."""

    document = snapshot.document
    codec = position_codec(document.text)
    references: dict[SourceSpan, BoundReference] = {}
    for item in bound_references(snapshot):
        if item.source_span is not None and item.source_span.filename == document.filename:
            references.setdefault(item.source_span, item)
    hints: list[_Hint] = []
    for node in walk_ast(snapshot.analysis.ast or snapshot.authoring.ast):
        if not isinstance(
            node, (ast.SourceCall, ast.SourceAction, ast.SourceMemberCall, ast.SourceMemberAction)
        ):
            continue
        if not any(_is_literal(item) for item in node.arguments):
            continue
        callee, span = _callee(node)
        if span is None or span.filename != document.filename:
            continue
        reference = references.get(span)
        if reference is None and "." in callee:
            # A dotted receiver call records only its final member segment.
            member = qualified_segment_spans(callee, span)[-1]
            reference = None if member is None else references.get(member)
        if reference is None or not (parameters := _parameters(snapshot, reference)):
            continue
        if reference.member_form is not None:
            callee = callee.rsplit(".", 1)[-1]
        if len(parameters) == 1 and (
            (name := parameters[0][0]) in _GENERIC_NAMES or name.casefold() in callee.casefold()
        ):
            continue
        for (name, key), argument in zip(parameters, node.arguments, strict=False):
            argument_span = getattr(argument, "source_span", None)
            if key and isinstance(argument, ast.SourceLiteral) and isinstance(argument.value, str):
                continue
            if (
                _is_literal(argument)
                and argument_span is not None
                and argument_span.filename == document.filename
            ):
                hints.append(_Hint(codec.offsets(argument_span)[0], f"{name}:"))
    # Macro and template bodies are walked once, but keep the result canonical.
    return sorted(set(hints), key=lambda item: (item.offset, item.label))


def inlay_hints(snapshot: Snapshot, range_: types.Range, encoding: str) -> list[types.InlayHint]:
    codec = position_codec(snapshot.document.text, encoding=encoding)
    start, end = codec.offset(range_.start), codec.offset(range_.end)
    return [
        types.InlayHint(
            position=codec.position(hint.offset),
            label=hint.label,
            kind=types.InlayHintKind.Parameter,
            padding_right=True,
        )
        for hint in collect_hints(snapshot)
        if start <= hint.offset <= end
    ]
