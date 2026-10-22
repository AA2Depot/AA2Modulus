"""Terminal settings: ANSI color, console capability and resolved render options."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TextIO

DiagnosticFormat = Literal["human", "short"]
ColorMode = Literal["auto", "always", "never"]

UNICODE_SEPARATOR = " › "
ASCII_SEPARATOR = " > "

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
BLUE = "\x1b[34m"
SEVERITY_STYLE = {"error": RED, "warning": YELLOW, "info": CYAN}


@dataclass(frozen=True, slots=True)
class ReportSettings:
    """User-chosen rendering options, before a stream decides about color."""

    format: DiagnosticFormat = "human"
    color: ColorMode = "auto"
    verbose: bool = False


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Rendering options resolved for one output stream."""

    format: DiagnosticFormat = "human"
    color: bool = False
    verbose: bool = False
    separator: str = UNICODE_SEPARATOR


def use_color(
    mode: ColorMode,
    stream: TextIO,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Decide whether ``stream`` should receive ANSI color.

    ``--color always|never`` beats the environment. Under ``auto``, ``NO_COLOR``
    disables, ``FORCE_COLOR`` (not ``0``) enables, ``TERM=dumb`` disables, and
    otherwise only a terminal is colored.
    """

    if mode == "never":
        return False
    if mode == "always":
        return True
    env = os.environ if environ is None else environ
    if env.get("NO_COLOR"):
        return False
    force = env.get("FORCE_COLOR")
    if force and force != "0":
        return True
    if env.get("TERM") == "dumb":
        return False
    try:
        is_tty = bool(stream.isatty())
    except (AttributeError, ValueError):
        return False
    return is_tty and _enable_virtual_terminal(stream)


def _enable_virtual_terminal(stream: TextIO) -> bool:
    """Enable ANSI processing on a Windows console; true elsewhere."""

    if sys.platform != "win32":
        return True
    try:
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
        handle = msvcrt.get_osfhandle(stream.fileno())  # type: ignore[attr-defined,unused-ignore]
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if mode.value & enable_vt:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | enable_vt))
    except (OSError, ValueError, AttributeError, ImportError):
        return False


def _separator(stream: TextIO) -> str:
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        UNICODE_SEPARATOR.encode(encoding)
    except (UnicodeError, LookupError):
        return ASCII_SEPARATOR
    return UNICODE_SEPARATOR


def render_options(
    settings: ReportSettings,
    stream: TextIO,
    *,
    environ: Mapping[str, str] | None = None,
) -> RenderOptions:
    """Resolve user settings for one stream (color and breadcrumb separator)."""

    return RenderOptions(
        format=settings.format,
        color=use_color(settings.color, stream, environ=environ),
        verbose=settings.verbose,
        separator=_separator(stream),
    )


def paint(text: str, enabled: bool, *styles: str) -> str:
    if not enabled or not text:
        return text
    return "".join(styles) + text + RESET
