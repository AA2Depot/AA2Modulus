"""The release manifest: the compatibility facts a build's ``initialize`` result advertises."""

from __future__ import annotations

from typing import Any

from ..context.operation import SourceContext
from ..syntax.lexicon import source_lexicon
from ..version import __version__

SCHEMA = "aa2modulus.release-manifest.v1"
# Increments only on a breaking wire change; additive features add a flag instead.
CONTRACT_VERSION = 1
BUILTIN_CATALOG = "builtinCatalog"
# Every additive flag the server can offer; initialize sets one only for a client that supports it.
FEATURES = (BUILTIN_CATALOG,)


def server_features(*, context: SourceContext) -> dict[str, Any]:
    """The flag-independent part of ``experimental.aa2modulus`` in the initialize result."""

    return {
        "contractVersion": CONTRACT_VERSION,
        "syntax": {
            "version": context.source_policy.language_version,
            "fingerprint": source_lexicon().fingerprint,
        },
    }


def editor_manifest(*, context: SourceContext | None = None) -> dict[str, Any]:
    context = context or SourceContext.create()
    return {
        "schema": SCHEMA,
        "version": __version__,
        **server_features(context=context),
        "features": dict.fromkeys(FEATURES, True),
    }
