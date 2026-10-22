"""The accepted source forms of one native target."""

from __future__ import annotations

from dataclasses import replace

from ...core.source_names import is_source_name, source_identifier
from ...metadata.identities import NativeMetadata, native_key
from ...metadata.snapshot import MetadataSnapshot
from ...model.native import ActionMetadata, EventMetadata, ExpressionMetadata, NamedConstantMetadata
from ...model.types import EXPR_PAYLOAD_MARKERS, ValueType
from ..policy import LanguagePolicy
from .model import FormKind, NativeTarget, SourceForm
from .spellings import policy_names, spellings


def target_forms(
    target: NativeTarget, metadata: MetadataSnapshot, policy: LanguagePolicy
) -> tuple[tuple[SourceForm, ...], tuple[str, ...]]:
    """Return the accepted forms and the native spellings a canonical name retires."""

    wire = target.wire
    member = policy.member_form_for_target(wire)
    output: list[SourceForm] = []
    for spelling in _target_spellings(target, metadata, policy):
        form = _spelling_form(target, spelling, metadata, policy)
        if form is not None:
            output.append(form)
    if member is not None:
        # A card-first target is written only as a member of its receiver card;
        # every flat spelling, native or former, is retired.
        member_form = SourceForm(
            member.key,
            member.name,
            "member",
            wire,
            target.signature,
            tuple(range(len(target.signature.parameter_types))),
            True,
            canonical=True,
            member=member,
        )
        return (member_form,), tuple(form.spelling for form in output)
    retired: tuple[str, ...] = ()
    configured = {name.casefold() for name in policy_names(target.metadata, policy)}
    if configured:
        # A target with a canonical spelling accepts only that spelling.
        accepted = [form for form in output if form.spelling.casefold() in configured]
        if any(form.reversible for form in accepted):
            retired = tuple(form.spelling for form in output if form not in accepted)
            output = accepted
    selected = next((index for index, form in enumerate(output) if form.reversible), None)
    if selected is not None:
        output[selected] = replace(output[selected], canonical=True)
    return tuple(output), retired


def _target_spellings(
    target: NativeTarget, metadata: MetadataSnapshot, policy: LanguagePolicy
) -> list[str]:
    """Policy and native spellings; a verified constant adds same-value row names."""

    entry, wire = target.metadata, target.wire
    result = list(spellings(entry, policy))
    if isinstance(entry, NamedConstantMetadata) and entry.resolved_value is not None:
        known_spellings = {item.casefold() for item in result}
        for row in metadata.named_constants:
            if (
                row.value_type != entry.value_type
                or row.id != wire.identifier
                or row.resolved_value is None
                or row.resolved_value != entry.resolved_value
            ):
                continue
            for alias in (source_identifier(row.name), row.name, row.interactive_name):
                if alias and is_source_name(alias) and alias.casefold() not in known_spellings:
                    known_spellings.add(alias.casefold())
                    result.append(alias)
    return result


def _spelling_form(
    target: NativeTarget, spelling: str, metadata: MetadataSnapshot, policy: LanguagePolicy
) -> SourceForm | None:
    """The form one spelling gives the target, if it resolves to it."""

    entry, wire = target.metadata, target.wire
    candidates: tuple[NativeMetadata, ...]
    if isinstance(entry, ActionMetadata):
        candidates = policy.action_candidates(metadata, spelling)
        form_kind: FormKind = "call"
    elif isinstance(entry, EventMetadata):
        candidates = policy.event_candidates(metadata, spelling)
        form_kind = "call"
    elif isinstance(entry, ExpressionMetadata):
        if entry.id in EXPR_PAYLOAD_MARKERS:
            return None
        candidates = tuple(
            candidate
            for candidate in policy.expression_candidates(metadata, spelling)
            if candidate.return_type == entry.return_type
            and candidate.parameter_types == entry.parameter_types
        )
        form_kind = "call" if entry.parameter_types else "getter"
    else:
        # A native row name is not a spelling for a different positional ID.
        if entry.id != wire.identifier:
            return None
        candidates = policy.named_constant_candidates(metadata, spelling, entry.value_type)
        form_kind = "constant"
    candidates = tuple(candidate for candidate in candidates if native_key(candidate) == wire)
    if not candidates:
        return None
    reversible, reason = _reversibility(entry, candidates, spelling, metadata, policy)
    key = f"{wire.kind}:{wire.scope}:{wire.identifier}:{form_kind}:{spelling.casefold()}"
    return SourceForm(
        key,
        spelling,
        form_kind,
        wire,
        target.signature,
        tuple(range(len(target.signature.parameter_types))),
        reversible,
        reason=reason,
    )


def _reversibility(
    entry: NativeMetadata,
    candidates: tuple[NativeMetadata, ...],
    spelling: str,
    metadata: MetadataSnapshot,
    policy: LanguagePolicy,
) -> tuple[bool, str | None]:
    """Whether the spelling recovers exactly this target, and why not."""

    reversible = True
    reason = None
    if isinstance(entry, NamedConstantMetadata):
        for candidate in candidates:
            assert isinstance(candidate, NamedConstantMetadata)
            if candidate.resolved_value is None or candidate.resolved_value != entry.resolved_value:
                reversible, reason = False, "shadowed_or_unverified_constant_value"
        if any(
            not candidate.parameter_types and candidate.return_type == entry.value_type
            for candidate in policy.expression_candidates(metadata, spelling)
        ):
            reversible, reason = False, "bare_getter_precedence"
        # Equivalent same-wire duplicates are one target; unrelated wire IDs
        # remain candidates even when their underlying values happen to match.
        distinct = {
            native_key(candidate)
            for candidate in policy.named_constant_candidates(metadata, spelling, entry.value_type)
        }
    elif isinstance(entry, ExpressionMetadata):
        distinct = {
            native_key(candidate)
            for candidate in policy.expression_candidates(metadata, spelling)
            if candidate.return_type == entry.return_type
            and candidate.parameter_types == entry.parameter_types
        }
    elif isinstance(entry, ActionMetadata):
        distinct = {
            native_key(candidate) for candidate in policy.action_candidates(metadata, spelling)
        }
    else:
        distinct = {
            native_key(candidate) for candidate in policy.event_candidates(metadata, spelling)
        }
    if len(distinct) > 1:
        reversible, reason = False, "ambiguous_source_signature"
    if isinstance(entry, ActionMetadata) and ValueType.INVALID in entry.parameter_types:
        reversible, reason = False, "requires_structured_source_form"
    return reversible, reason
