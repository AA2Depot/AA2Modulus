"""Server construction and the stdio entry point."""

from __future__ import annotations

import logging

from lsprotocol import types
from pygls.exceptions import JsonRpcException

from ..commands.register import register_commands
from .app import AA2LanguageServer
from .handlers import code_actions, completion, lifecycle, navigation, presentation, rename, sync

_REFUSAL_CODES = frozenset(
    {types.LSPErrorCodes.RequestFailed.value, types.LSPErrorCodes.ContentModified.value}
)


class _RefusalFilter(logging.Filter):
    """Drop pygls tracebacks for requests the server refused on purpose.

    Refused renames and commands answer the client with a message; they are not
    server faults, so only unexpected exceptions reach the log.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        error = record.exc_info[1] if record.exc_info else None
        return not (isinstance(error, JsonRpcException) and error.code in _REFUSAL_CODES)


def create_server() -> AA2LanguageServer:
    server = AA2LanguageServer()
    lifecycle.register(server)
    sync.register(server)
    navigation.register(server)
    rename.register(server)
    presentation.register(server)
    code_actions.register(server)
    completion.register(server)
    register_commands(server)
    return server


def run_server() -> None:
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("pygls.protocol.json_rpc").addFilter(_RefusalFilter())
    server = create_server()
    try:
        server.start_io()
    finally:
        server.executor.shutdown(wait=False, cancel_futures=True)
        server.scan_executor.shutdown(wait=False, cancel_futures=True)
