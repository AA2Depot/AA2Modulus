"""Suite-wide fixtures; every test must live in one of the area directories."""

from __future__ import annotations

import pytest

from aa2modulus.metadata.loader import load_metadata
from aa2modulus.metadata.snapshot import MetadataSnapshot
from tests.support.fixture_data import MODULE_NAMES
from tests.support.paths import MODULE_FIXTURES, TESTS_ROOT

SUITE_DIRECTORIES = {"source", "binary", "metadata", "cli", "lsp"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        directory = item.path.relative_to(TESTS_ROOT).parts[0]
        if directory not in SUITE_DIRECTORIES:
            raise pytest.UsageError(f"Test module has no owner directory: {item.path}")
        item.add_marker(getattr(pytest.mark, directory))


@pytest.fixture(scope="session")
def metadata() -> MetadataSnapshot:
    return load_metadata()


@pytest.fixture(params=MODULE_NAMES, ids=MODULE_NAMES)
def module_fixture(request: pytest.FixtureRequest) -> tuple[str, bytes]:
    name = request.param
    return name, (MODULE_FIXTURES / name).read_bytes()
