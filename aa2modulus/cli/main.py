"""Command-line interface for AAUnlimited module inspection."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from typing import Protocol

from ..context.limits import SourceLimits
from ..metadata.schema import MetadataError
from ..version import __version__
from .arguments import report_settings_from_args, source_limits_from_args
from .commands import compile as compile_command
from .commands import decompile, inspect, validate
from .common import EXIT_INTERNAL_ERROR, EXIT_OK, EXIT_USAGE_ERROR
from .render.terminal import ReportSettings

VERSION_TEXT = f"aa2modulus {__version__}"


class _Command(Protocol):
    """What each ``commands`` module provides."""

    def add_parser(self, commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None: ...

    def run(
        self, args: argparse.Namespace, settings: ReportSettings, source_limits: SourceLimits | None
    ) -> int: ...


_COMMANDS: dict[str, _Command] = {
    "inspect": inspect,
    "validate": validate,
    "compile": compile_command,
    "decompile": decompile,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aa2modulus",
        description="Read, validate, compile, and inspect AAUnlimited modules.",
    )
    parser.add_argument("--version", action="version", version=VERSION_TEXT)
    commands = parser.add_subparsers(dest="command")
    for command in _COMMANDS.values():
        command.add_parser(commands)
    lsp_parser = commands.add_parser(
        "lsp-server",
        help="run the .aa2m language server over stdio",
        description="Run the .aa2m language server over stdio for an editor client.",
    )
    lsp_parser.add_argument("--version", action="version", version=VERSION_TEXT)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "lsp-server":
        from ..lsp.server.run import run_server

        try:
            run_server()
        except MetadataError as exc:
            print(f"metadata error: {exc}", file=sys.stderr)
            return EXIT_INTERNAL_ERROR
        return EXIT_OK
    command = _COMMANDS.get(args.command)
    if command is None:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE_ERROR
    source_limits: SourceLimits | None = None
    if args.command in {"validate", "compile"}:
        try:
            source_limits = source_limits_from_args(args)
        except ValueError as exc:
            parser.error(str(exc))
    return command.run(args, report_settings_from_args(args), source_limits)
