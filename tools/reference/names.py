"""Source spellings of a native row, as the language catalog binds them"""

from __future__ import annotations

from typing import Any

from aa2modulus.core.source_names import source_identifier
from aa2modulus.language.catalog.model import LanguageCatalog, SourceForm
from aa2modulus.metadata.identities import native_key
from aa2modulus.model.native import NamedConstantMetadata


def source_names(entry: Any, catalog: LanguageCatalog) -> dict[str, Any]:
    wire = native_key(entry)
    target = catalog.native_targets[wire]

    # A shadowed constant row has no spelling: its ID selects another row's value.
    forms = target.forms
    if (
        isinstance(entry, NamedConstantMetadata)
        and isinstance(target.metadata, NamedConstantMetadata)
        and entry.resolved_value != target.metadata.resolved_value
    ):
        forms = ()

    spellings = [spelling(form) for form in forms]
    ambiguity = {
        spelling(form): len(catalog.candidates(wire.kind, form.spelling)) > 1 for form in forms
    }
    generated = source_identifier(entry.name)

    return {
        "registry": entry.name,
        "interactive": entry.interactive_name,
        "generated": [generated] if generated else [],
        "symbol": getattr(entry, "symbol", None),
        "preferred": next((spelling(form) for form in forms if form.canonical), None),
        "candidates": spellings,
        "ambiguity": ambiguity,
    }


def spelling(form: SourceForm) -> str:
    """A card-first target is written only as a member of its receiver: ``<card>.SetVirtue``."""

    if form.member is None:
        return form.spelling
    return f"<{form.member.receiver_role}>.{form.member.name}"
