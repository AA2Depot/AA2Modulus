"""Locate and load the shipped source-language policy."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from ..metadata.loader import load_metadata
from ..metadata.schema import MetadataError
from ..metadata.snapshot import MetadataSnapshot
from .policy import LanguagePolicy
from .reader import read_source_policy
from .validation.policy import validate_policy

LANGUAGE_POLICY = "policy.toml"

_shipped: tuple[Path, MetadataSnapshot, LanguagePolicy] | None = None
_shipped_lock = Lock()


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
    The shipped policy is read once per metadata snapshot and process.
    """

    global _shipped
    if metadata is None:
        metadata = load_metadata()
    if path is not None:
        return _read_policy(path, metadata)
    policy_path = language_policy_path()
    shipped = _shipped
    if not _is_shipped(shipped, policy_path, metadata):
        with _shipped_lock:
            shipped = _shipped
            if not _is_shipped(shipped, policy_path, metadata):
                shipped = (policy_path, metadata, _read_policy(policy_path, metadata))
                _shipped = shipped
    assert shipped is not None
    return shipped[2]


def _is_shipped(
    shipped: tuple[Path, MetadataSnapshot, LanguagePolicy] | None,
    policy_path: Path,
    metadata: MetadataSnapshot,
) -> bool:
    return shipped is not None and shipped[0] == policy_path and shipped[1] is metadata


def _read_policy(policy_path: Path, metadata: MetadataSnapshot) -> LanguagePolicy:
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
