"""The ``editor-data catalog`` document: header, entries and its JSON text."""

from __future__ import annotations

import json
from typing import Any

from ...context.operation import SourceContext
from ...language.documentation import DOCS_WEBSITE
from . import entries, examples
from .entries import Report

SCHEMA = "aa2modulus.editor-builtins.v1"


def editor_catalog(*, context: SourceContext | None = None) -> tuple[dict[str, Any], Report]:
    context = context or SourceContext.create()
    report = Report()

    drafts = entries.build(context, report)
    examples.attach(context, drafts, report)

    document = {
        "schema": SCHEMA,
        "languageVersion": context.source_policy.language_version,
        "catalogFingerprint": context.catalog.fingerprint,
        "website": DOCS_WEBSITE,
        "entries": [draft.entry for draft in drafts],
    }
    return document, report


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"
