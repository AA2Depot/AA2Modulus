"""Source spellings of native targets under the language policy."""

from __future__ import annotations

from ...core.source_names import is_source_name, source_identifier
from ...metadata.identities import NativeMetadata, native_key
from ..policy import LanguagePolicy


def policy_names(entry: NativeMetadata, policy: LanguagePolicy) -> tuple[str, ...]:
    """The spelling the policy configures: the preferred name (events: the symbol).

    Empty for a target without a canonical source spelling; such a target keeps every
    native spelling.
    """

    first = preferred_name(entry, policy) or getattr(entry, "symbol", None)
    if not first or not is_source_name(first):
        return ()
    return (first,)


def spellings(entry: NativeMetadata, policy: LanguagePolicy) -> tuple[str, ...]:
    names = (
        preferred_name(entry, policy),
        getattr(entry, "symbol", None),
        source_identifier(entry.name),
        entry.name,
        entry.interactive_name,
    )
    output: dict[str, str] = {}
    for name in names:
        if name and is_source_name(name):
            output.setdefault(name.casefold(), name)
    return tuple(output.values())


def preferred_name(entry: NativeMetadata, policy: LanguagePolicy) -> str | None:
    wire = native_key(entry)
    if wire.kind == "action":
        return policy.preferred_action_name(wire.identifier)
    if wire.kind == "event":
        return None
    assert wire.scope is not None
    if wire.kind == "expression":
        return policy.preferred_expression_name(wire.scope, wire.identifier)
    return policy.preferred_named_constant_name(wire.scope, wire.identifier)
