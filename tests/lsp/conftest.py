"""The shared source context and language-server client fixtures."""

from __future__ import annotations

import pytest

from aa2modulus.context.operation import SourceContext
from tests.support.lsp_client import Client


@pytest.fixture(scope="session")
def context() -> SourceContext:
    return SourceContext.create()


@pytest.fixture(scope="module")
def client():
    connection = Client()
    try:
        yield connection
        connection.finish()
    finally:
        if connection.process.poll() is None:
            connection.process.terminate()
            connection.process.wait(timeout=10)


@pytest.fixture(scope="module")
def snippet_client():
    connection = Client(snippet_support=True)
    try:
        yield connection
        connection.finish()
    finally:
        if connection.process.poll() is None:
            connection.process.terminate()
            connection.process.wait(timeout=10)
