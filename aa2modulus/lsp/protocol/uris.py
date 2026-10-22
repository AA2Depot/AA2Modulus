"""Pure file-URI helpers for mapping editor documents to native file identities."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote_to_bytes, urlsplit

_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_WINDOWS_DRIVE = re.compile(r"^/?([A-Za-z]):(?:/|$)")


def file_uri_path(uri: str, *, windows: bool = False) -> str | None:
    """Decode a valid file URI to a path using the requested path syntax.

    This function performs no filesystem access, so Windows drive and UNC URI
    syntax can be checked on any host by passing ``windows=True``.
    """

    if not isinstance(uri, str) or "\x00" in uri or "?" in uri or "#" in uri:
        return None
    if _BAD_ESCAPE.search(uri):
        return None
    try:
        parsed = urlsplit(uri)
        if parsed.scheme.lower() != "file" or parsed.username or parsed.password:
            return None
        path = _decode(parsed.path)
        authority = _decode(parsed.netloc)
    except (UnicodeDecodeError, ValueError):
        return None
    if not path or "\x00" in path or "\x00" in authority:
        return None

    if windows:
        if authority and authority.lower() != "localhost":
            if "/" in authority or "\\" in authority or ":" in authority:
                return None
            if not path.startswith("/") or path == "/":
                return None
            return "\\\\" + authority + path.replace("/", "\\")
        match = _WINDOWS_DRIVE.match(path)
        if match is None:
            return None
        drive = match.group(1)
        tail = path[match.end() :]
        return f"{drive}:\\" + tail.replace("/", "\\")

    if authority and authority.lower() != "localhost":
        return None
    if not path.startswith("/") or _WINDOWS_DRIVE.match(path):
        return None
    return path


def file_identity(uri: str) -> str | None:
    """Return the canonical native path identity for a local file URI."""

    path = file_uri_path(uri, windows=os.name == "nt")
    if path is None:
        return None
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except (OSError, RuntimeError, ValueError):
        return None


def identity_uri(identity: str) -> str:
    """Return the canonical file URI for a native path identity."""

    if not isinstance(identity, str):
        raise TypeError("identity must be a string")
    if "\x00" in identity:
        raise ValueError("identity cannot contain NUL")
    try:
        return Path(identity).resolve().as_uri()
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("identity must be a valid native filesystem path") from error


def _decode(value: str) -> str:
    return unquote_to_bytes(value).decode("utf-8", errors="strict")
