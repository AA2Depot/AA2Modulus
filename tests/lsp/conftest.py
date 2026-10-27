"""Language-server clients: shared per-session servers and a factory for private ones.

The shared clients live as long as the test session, so each test that uses one
opens documents under URIs no other test uses (its own ``tmp_path`` or a name
unique to the test) and never relies on documents another test left open.
"""

from __future__ import annotations

from contextlib import ExitStack

import pytest

from tests.support.lsp_client import Client, serving

# Every optional client capability the server reacts to, for the one shared
# client that exercises them all.
FULL_CAPABILITIES = {
    "textDocument": {"rename": {"prepareSupport": True}},
    "workspace": {
        "textDocumentContent": {"dynamicRegistration": True},
        "workspaceEdit": {"documentChanges": True},
        "didChangeWatchedFiles": {"dynamicRegistration": True},
        "semanticTokens": {"refreshSupport": True},
    },
    "window": {"showDocument": {"support": True}},
}


@pytest.fixture(scope="session")
def client():
    """A client that advertises no optional capability."""

    with serving() as connection:
        yield connection


@pytest.fixture(scope="session")
def full_client():
    """A client that advertises snippets and every capability in ``FULL_CAPABILITIES``.

    The server's file-watcher registration is answered at start and kept as
    ``registration``.
    """

    with serving(snippet_support=True, capabilities=FULL_CAPABILITIES) as connection:
        connection.registration = connection.respond("client/registerCapability")
        yield connection


@pytest.fixture
def start_client():
    """Start a private server for one test; it is shut down when the test ends."""

    with ExitStack() as stack:

        def start(*args, **options) -> Client:
            return stack.enter_context(serving(*args, **options))

        yield start
