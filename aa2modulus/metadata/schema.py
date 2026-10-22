"""Shared schema identifiers for generated and runtime metadata."""

from __future__ import annotations


class MetadataError(ValueError):
    """Raised when metadata is missing, malformed, or inconsistent."""


MANIFEST_SCHEMA = "aa2modulus.metadata-manifest.v3"
FILE_SCHEMAS = {
    "actions.json": "aa2modulus.actions.v3",
    "events.json": "aa2modulus.events.v3",
    "expressions.json": "aa2modulus.expressions.v3",
    "named_constants.json": "aa2modulus.named_constants.v3",
}
GENERATOR_VERSION = "4"
SCOPE_TYPES = {"invalid": 0, "int": 1, "bool": 2, "float": 3, "string": 4}
