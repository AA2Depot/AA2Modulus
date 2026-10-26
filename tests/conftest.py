"""Suite-wide fixtures; every test must live in one of the area directories."""

from __future__ import annotations

import os

import pytest

from aa2modulus.context.operation import SourceContext
from aa2modulus.metadata.loader import load_metadata
from aa2modulus.metadata.snapshot import MetadataSnapshot
from tests.support.fixture_data import MODULE_NAMES
from tests.support.paths import MODULE_FIXTURES, TESTS_ROOT

SUITE_DIRECTORIES = {"source", "binary", "metadata", "cli", "lsp"}


def pytest_configure(config: pytest.Config) -> None:
    # The developer's color settings would change CLI output; tests that need
    # them pass them explicitly.
    for name in ("FORCE_COLOR", "NO_COLOR"):
        os.environ.pop(name, None)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        directory = item.path.relative_to(TESTS_ROOT).parts[0]
        if directory not in SUITE_DIRECTORIES:
            raise pytest.UsageError(f"Test module has no owner directory: {item.path}")
        item.add_marker(getattr(pytest.mark, directory))


@pytest.fixture(scope="session")
def metadata() -> MetadataSnapshot:
    return load_metadata()


@pytest.fixture(scope="session")
def context(metadata: MetadataSnapshot) -> SourceContext:
    return SourceContext.create(metadata=metadata)


@pytest.fixture(params=MODULE_NAMES, ids=MODULE_NAMES)
def module_fixture(request: pytest.FixtureRequest) -> tuple[str, bytes]:
    name = request.param
    return name, (MODULE_FIXTURES / name).read_bytes()
