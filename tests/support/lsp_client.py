"""A test client that drives the language server over stdio in a child process."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from tests.support.paths import ROOT


def _frame(message: dict) -> bytes:
    payload = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload


class Client:
    #: The answered ``client/registerCapability`` request, when the owner of the client kept it.
    registration: dict | None = None

    def __init__(
        self,
        encodings=None,
        *,
        initialization_options=None,
        snippet_support=False,
        capabilities=None,
        workspace_folders=None,
    ):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "aa2modulus", "lsp-server"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.received = queue.Queue()
        self.saved = []
        self.next_id = 0
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        extra = capabilities or {}
        capabilities = {"general": {"positionEncodings": encodings}} if encodings else {}
        if snippet_support:
            capabilities["textDocument"] = {
                "completion": {"completionItem": {"snippetSupport": True}}
            }
        for key, value in extra.items():
            capabilities[key] = {**capabilities.get(key, {}), **value}
        parameters = {"processId": None, "capabilities": capabilities}
        if workspace_folders is not None:
            parameters["workspaceFolders"] = workspace_folders
        if initialization_options is not None:
            parameters["initializationOptions"] = initialization_options
        try:
            self.initialized = self.request("initialize", parameters)
        except (queue.Empty, EOFError, AssertionError):
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait(timeout=10)
            self.reader.join(timeout=1)
            raise AssertionError(
                self.process.stderr.read().decode() or "no initialize response"
            ) from None
        self.send("initialized", {})

    def read(self):
        try:
            stream = self.process.stdout
            while True:
                header = stream.readline()
                if not header:
                    self.received.put(EOFError("server stdout closed"))
                    return
                assert header.startswith(b"Content-Length:"), header
                size = int(header.split(b":", 1)[1])
                while stream.readline() not in (b"\r\n", b"\n"):
                    pass
                self.received.put(json.loads(stream.read(size)))
        except (AssertionError, ValueError, OSError) as exc:
            self.received.put(exc)

    def send(self, method, params, *, request=False):
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if request:
            self.next_id += 1
            message["id"] = self.next_id
        self.process.stdin.write(_frame(message))
        self.process.stdin.flush()
        return message.get("id")

    def request_canceled(self, method, params):
        """Send a request and its ``$/cancelRequest`` in one write; return the reply.

        The server reads both frames before any answer can leave, so a request
        that needs an analysis pass is canceled while it is still waiting.
        """

        self.next_id += 1
        identifier = self.next_id
        request = {"jsonrpc": "2.0", "method": method, "params": params, "id": identifier}
        cancel = {"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": identifier}}
        self.process.stdin.write(_frame(request) + _frame(cancel))
        self.process.stdin.flush()
        return self.wait(lambda item: item.get("id") == identifier)

    def wait(self, predicate, timeout=10):
        for index, message in enumerate(self.saved):
            if predicate(message):
                return self.saved.pop(index)
        deadline = time.monotonic() + timeout
        while True:
            message = self.received.get(timeout=max(0.01, deadline - time.monotonic()))
            if isinstance(message, Exception):
                raise message
            if predicate(message):
                return message
            self.saved.append(message)

    def request(self, method, params):
        identifier = self.send(method, params, request=True)
        message = self.wait(lambda item: item.get("id") == identifier)
        assert "error" not in message, message
        return message["result"]

    def request_error(self, method, params):
        identifier = self.send(method, params, request=True)
        message = self.wait(lambda item: item.get("id") == identifier)
        assert "error" in message, message
        return message["error"]

    def respond(self, method, result=None):
        """Answer the next server-to-client request for ``method``."""

        message = self.wait(lambda item: item.get("method") == method and "id" in item)
        self.process.stdin.write(_frame({"jsonrpc": "2.0", "id": message["id"], "result": result}))
        self.process.stdin.flush()
        return message.get("params")

    def open(self, uri, source, version=1, language_id="aa2m"):
        self.send(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": version,
                    "text": source,
                }
            },
        )

    def change(self, uri, source, version):
        self.send(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": source}],
            },
        )

    def diagnostics(self, uri, predicate=lambda items: True, version=None):
        message = self.wait(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == uri
                and (version is None or item["params"].get("version") == version)
                and predicate(item["params"]["diagnostics"])
            )
        )
        return message["params"]["diagnostics"]

    def forget(self, predicate: Callable[[dict], bool]) -> None:
        """Drop the saved messages that match ``predicate``."""

        self.saved[:] = [message for message in self.saved if not predicate(message)]

    @contextmanager
    def folder(self, path: Path, name: str = "folder") -> Iterator[None]:
        """Add ``path`` to the workspace folders for the length of the block."""

        entry = {"uri": path.as_uri(), "name": name}
        self.send(
            "workspace/didChangeWorkspaceFolders", {"event": {"added": [entry], "removed": []}}
        )
        try:
            yield
        finally:
            self.send(
                "workspace/didChangeWorkspaceFolders", {"event": {"added": [], "removed": [entry]}}
            )

    def finish(self):
        self.request("shutdown", None)
        self.send("exit", None)
        self.process.wait(timeout=10)
        assert self.process.returncode == 0
        assert self.process.stderr.read() == b""

    def stop(self) -> None:
        """Terminate the server if it is still running."""

        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)


@contextmanager
def serving(*args, **options) -> Iterator[Client]:
    """Start a server; leaving the block shuts it down cleanly and checks its exit."""

    connection = Client(*args, **options)
    try:
        yield connection
        connection.finish()
    finally:
        connection.stop()
