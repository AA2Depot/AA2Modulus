"""Locate and load the shipped source-language policy."""

from __future__ import annotations

from pathlib import Path

from ..metadata.loader import load_metadata
from ..metadata.schema import MetadataError
from ..metadata.snapshot import MetadataSnapshot
from .policy import LanguagePolicy
from .reader import read_source_policy
from .validation.policy import validate_policy

LANGUAGE_POLICY = "policy.toml"


def language_policy_path() -> Path:
    """Return the package-owned source-language policy."""

    return Path(__file__).resolve().parent / LANGUAGE_POLICY


def load_language_policy(
    *,
    metadata: MetadataSnapshot | None = None,
    path: Path | None = None,
) -> LanguagePolicy:
    """Load and validate the shipped policy (or the file at ``path``) against metadata.

    This is the only place a policy is validated; catalogs and contexts trust it.
    """

    if metadata is None:
        metadata = load_metadata()
    policy_path = language_policy_path() if path is None else path
    try:
        policy = read_source_policy(policy_path, metadata)
    except (OSError, ValueError, TypeError) as exc:
        raise MetadataError(f"invalid source language policy {policy_path}: {exc}") from exc
    # Provider failures are programming/configuration integration errors, not
    # TOML conversion errors. Keep them outside the input-adaptation boundary.
    errors = validate_policy(policy, metadata)
    if errors:
        raise MetadataError(f"invalid source language policy {policy_path}: " + "; ".join(errors))
    return policy
