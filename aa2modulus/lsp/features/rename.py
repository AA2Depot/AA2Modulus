"""Rebinding-validated rename for authored declarations.

A rename edits each occurrence in the form its site needs and is accepted only
when analyzing the edited texts binds the same sites to the same targets, with
no new error.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from lsprotocol import types

from ...context.operation import SourceContext
from ...core.locations import SourceSpan
from ...core.source_names import is_source_name
from ...hir.symbols import BoundReference
from ...syntax import ast
from ..protocol.positions import PositionCodec, position_codec
from ..workspace.documents import Snapshot, analyze_document
from .lookup import bound_references, declaration_span, reference_at
from .references import Occurrence, Sites, Target, occurrences, sites_of, target_at


class RenameError(Exception):
    """A rename the server refuses; the message is shown to the user."""


class StaleRename(RenameError):
    """The analyses in scope no longer agree with the current texts."""


def texts_in_scope(snapshots: Iterable[Snapshot]) -> dict[str, str]:
    """One text per file; analyses that disagree mean a file changed mid-request."""

    texts: dict[str, str] = {}
    for snapshot in snapshots:
        for filename, text in snapshot.texts.items():
            if texts.setdefault(filename, text) != text:
                raise StaleRename(f"{filename} changed while the request ran; try again")
    return texts


def prepare_rename(
    snapshot: Snapshot, position: types.Position, encoding: str
) -> types.PrepareRenamePlaceholder | None:
    reference = reference_at(snapshot, position, encoding)
    if reference is not None and reference.declaration is None:
        if reference.metadata is not None:
            raise RenameError(f"'{reference.name}' is a built-in and cannot be renamed")
        raise RenameError(f"'{reference.name}' has no authored declaration to rename")
    target = target_at(snapshot, position, encoding)
    if target is None or target.span.filename not in snapshot.texts:
        return None
    span = reference.source_span if reference is not None else target.span
    assert span is not None
    codec = position_codec(snapshot.document.text, encoding=encoding)
    return types.PrepareRenamePlaceholder(codec.range(span), target.name)


@dataclass(frozen=True, slots=True)
class TextChange:
    """A replacement of ``text[start:end]``; ``inner`` locates the name inside it."""

    start: int
    end: int
    text: str
    inner: int = 0


@dataclass(frozen=True, slots=True)
class FileChanges:
    text: str
    changes: tuple[TextChange, ...]
    edited: str = field(init=False)

    def __post_init__(self) -> None:
        parts = []
        cursor = 0
        for change in self.changes:
            if change.start < cursor:
                raise RenameError("overlapping rename sites")
            parts.append(self.text[cursor : change.start])
            parts.append(change.text)
            cursor = change.end
        parts.append(self.text[cursor:])
        object.__setattr__(self, "edited", "".join(parts))

    def offset(self, offset: int) -> int | None:
        """Map an offset in ``text`` to ``edited``; a renamed site maps to its name."""

        shift = 0
        for change in self.changes:
            if change.start == offset:
                return offset + shift + change.inner
            if change.end <= offset:
                shift += len(change.text) - (change.end - change.start)
            elif change.start < offset:
                return None
            else:
                break
        return offset + shift


def _kind(target: Target, sites: Sites) -> str:
    declaration = target.declaration
    if isinstance(declaration, ast.SourceParameter):
        return "slot" if target.span in sites.slots else "parameter"
    return {
        ast.SourceGlobal: "global",
        ast.SourceLocal: "local",
        ast.SourceMacro: "macro",
        ast.SourceTriggerTemplate: "template",
        ast.SourceConstant: "constant",
    }[type(declaration)]


def _quoted(name: str) -> str:
    return json.dumps(name, ensure_ascii=False)


def _check_name(name: str, kind: str, context: SourceContext) -> None:
    if not name:
        raise RenameError("The new name cannot be empty")
    if kind != "template" and name.casefold() in context.catalog.protected_names:
        raise RenameError(f"'{name}' is a protected built-in name")
    if kind in {"macro", "slot"} and not is_source_name(name, allow_qualified=False):
        raise RenameError(f"{kind.capitalize()} names must be non-keyword identifiers")


def _change(
    item: Occurrence,
    codec: PositionCodec,
    *,
    old: str,
    new: str,
    kind: str,
    bare: bool,
    sites: Sites,
) -> TextChange:
    start, end = codec.offsets(item.span)
    token = codec.text[start:end]
    if token.startswith('"'):
        try:
            current = json.loads(token)
        except ValueError:
            current = None
        if current != old:
            raise StaleRename(f"'{old}' changed while the request ran; try again")
        text = _quoted(new)
        if item.span in sites.unnamed_imports:
            # Keep the instantiated trigger's serialized name.
            text += f" {_quoted(old)}"
        return TextChange(start, end, text)
    if (token.casefold() != old.casefold()) if kind == "macro" else (token != old):
        raise StaleRename(f"'{old}' changed while the request ran; try again")
    if bare:
        return TextChange(start, end, new)
    if item.declaration or item.span in sites.loop_targets:
        return TextChange(start, end, _quoted(new))
    form = "const" if kind == "constant" else "variable"
    return TextChange(start, end, f"{form}({_quoted(new)})", len(form) + 1)


@dataclass(frozen=True, slots=True)
class RenamePlan:
    target: Target
    kind: str
    files: dict[str, FileChanges]


def plan_rename(
    snapshots: Sequence[Snapshot], target: Target, new_name: str, context: SourceContext
) -> RenamePlan:
    """Edits for every occurrence, written in the form each site needs."""

    relevant = [item for item in snapshots if target.span.filename in item.texts]
    if not relevant:
        raise StaleRename(f"'{target.name}' is no longer declared here; try again")
    sites = _mergesites_of(relevant)
    kind = _kind(target, sites)
    _check_name(new_name, kind, context)
    texts = texts_in_scope(relevant)
    bare = is_source_name(new_name, allow_qualified=False) and (
        new_name.casefold() not in context.catalog.protected_names
    )
    grouped: dict[str, list[TextChange]] = {}
    if new_name != target.name:
        codecs: dict[str, PositionCodec] = {}
        for span, item in occurrences(relevant, target).items():
            codec = codecs.get(span.filename)
            if codec is None:
                codec = codecs[span.filename] = position_codec(texts[span.filename])
            grouped.setdefault(span.filename, []).append(
                _change(
                    item, codec, old=target.name, new=new_name, kind=kind, bare=bare, sites=sites
                )
            )
    files = {
        filename: FileChanges(texts[filename], tuple(sorted(changes, key=lambda c: c.start)))
        for filename, changes in grouped.items()
    }
    return RenamePlan(target, kind, files)


def _mergesites_of(snapshots: Iterable[Snapshot]) -> Sites:
    parts = [sites_of(item) for item in snapshots]
    return Sites(
        frozenset().union(*(item.writes for item in parts)),
        frozenset().union(*(item.loop_targets for item in parts)),
        frozenset().union(*(item.unnamed_imports for item in parts)),
        frozenset().union(*(item.slots for item in parts)),
    )


type _SiteKey = tuple[str, int]
type _TargetKey = tuple[str, object]


def _site_targets(
    snapshot: Snapshot, key: Callable[[SourceSpan], _SiteKey | None]
) -> dict[_SiteKey, dict[_TargetKey, BoundReference]]:
    result: dict[_SiteKey, dict[_TargetKey, BoundReference]] = {}
    for reference in bound_references(snapshot):
        span = reference.source_span
        site = key(span) if span is not None else None
        if site is None:
            continue
        target: _TargetKey
        if reference.declaration is not None:
            declared = declaration_span(reference.declaration)
            target = ("declaration", key(declared) if declared is not None else None)
        elif reference.metadata is not None:
            target = ("built-in", reference.name.casefold())
        else:
            target = ("external", reference.name)
        result.setdefault(site, {}).setdefault(target, reference)
    return result


def _keyer(
    texts: Mapping[str, str], files: Mapping[str, FileChanges] | None = None
) -> Callable[[SourceSpan], _SiteKey | None]:
    codecs: dict[str, PositionCodec] = {}

    def key(span: SourceSpan) -> _SiteKey | None:
        text = texts.get(span.filename)
        if text is None:
            return None
        codec = codecs.get(span.filename)
        if codec is None:
            codec = codecs[span.filename] = position_codec(text)
        offset: int | None = codec.offsets(span)[0]
        changes = files.get(span.filename) if files is not None else None
        if changes is not None and offset is not None:
            offset = changes.offset(offset)
        return None if offset is None else (span.filename, offset)

    return key


def _where(span: SourceSpan | None) -> str:
    if span is None:
        return "an unknown location"
    return f"{Path(span.filename).name}:{span.start_line}:{span.start_column}"


def _describe(reference: BoundReference) -> str:
    declaration = reference.declaration
    if declaration is None:
        return f"the built-in '{reference.name}'"
    kind = {
        ast.SourceGlobal: "global",
        ast.SourceLocal: "local",
        ast.SourceParameter: "parameter",
        ast.SourceMacro: "macro",
        ast.SourceTriggerTemplate: "template",
        ast.SourceConstant: "constant",
    }.get(type(declaration), "declaration")
    return f"the {kind} '{declaration.name}' declared at {_where(declaration_span(declaration))}"


def check_rename(plan: RenamePlan, before: Snapshot, after: Snapshot, new_name: str) -> None:
    """Refuse a rename that changes another binding or introduces an error."""

    remaining = Counter(item.code for item in before.analysis.result.errors)
    for item in after.analysis.result.errors:
        if remaining[item.code]:
            remaining[item.code] -= 1
            continue
        raise RenameError(f"Renaming to '{new_name}' would cause an error: {item.message}")
    old_key = _keyer(before.texts, plan.files)
    renamed = ("declaration", old_key(plan.target.span))
    previous = _site_targets(before, old_key)
    current = _site_targets(after, _keyer(after.texts))
    for site, targets in previous.items():
        now = current.get(site)
        if renamed in targets:
            if now is None or renamed not in now:
                use = next(iter(targets.values())).source_span
                other = (
                    "no declaration"
                    if not now
                    else ", ".join(_describe(item) for item in now.values())
                )
                raise RenameError(
                    f"Renaming to '{new_name}' would make the use at {_where(use)} refer to "
                    f"{other} "
                    f"instead of the renamed {plan.kind}"
                )
        elif now is not None and now.keys() != targets.keys():
            original = next(iter(targets.values()))
            raise RenameError(
                f"Renaming to '{new_name}' would make '{original.name}' at "
                f"{_where(original.source_span)} "
                f"refer to the renamed {plan.kind} instead of {_describe(original)}"
                if renamed in now
                else f"Renaming would change what '{original.name}' at "
                f"{_where(original.source_span)} refers to"
            )


def validate_rename(
    plan: RenamePlan, snapshots: Sequence[Snapshot], new_name: str, context: SourceContext
) -> None:
    """Re-analyze each affected root with the edited texts and check its bindings."""

    edited = {filename: changes.edited for filename, changes in plan.files.items()}
    for before in snapshots:
        if not edited.keys() & before.texts.keys():
            continue
        document = before.document
        overlays = {**before.texts, **edited}
        overlays.pop(document.filename, None)
        after = analyze_document(
            replace(document, text=edited.get(document.filename, document.text)),
            context,
            overlays,
        )
        check_rename(plan, before, after, new_name)


def rename(
    snapshots: Sequence[Snapshot], target: Target, new_name: str, context: SourceContext
) -> RenamePlan:
    """Plan and validate a rename; raises ``RenameError`` when it is refused."""

    plan = plan_rename(snapshots, target, new_name, context)
    if plan.files:
        validate_rename(plan, snapshots, new_name, context)
    return plan
