"""Canonical repository and fixture paths for tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_METADATA = ROOT / "aa2modulus" / "metadata"
REGISTRY = PACKAGE_METADATA / "registry"
LANGUAGE = ROOT / "aa2modulus" / "language"
LANGUAGE_POLICY = LANGUAGE / "policy.toml"
TESTS_ROOT = ROOT / "tests"
FIXTURES = TESTS_ROOT / "fixtures"
MODULE_FIXTURES = FIXTURES / "modules"
