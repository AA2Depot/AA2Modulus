"""The lexicon document editors test their grammars against: header and lexicon groups."""

from __future__ import annotations

from typing import Any

from ..context.operation import SourceContext
from ..syntax.lexicon import source_lexicon

SCHEMA = "aa2modulus.editor-lexicon.v1"


def editor_lexicon(*, context: SourceContext | None = None) -> dict[str, Any]:
    context = context or SourceContext.create()
    lexicon = source_lexicon()
    return {
        "schema": SCHEMA,
        "languageVersion": context.source_policy.language_version,
        "fingerprint": lexicon.fingerprint,
        **lexicon.data(),
    }
