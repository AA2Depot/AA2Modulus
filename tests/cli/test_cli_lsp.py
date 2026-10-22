"""Server dispatch preserves dependency-free help and ordinary CLI workflows."""

from __future__ import annotations

import subprocess
import sys
import tomllib

import pytest

from aa2modulus.version import __version__
from tests.support.paths import ROOT


def test_version_matches_project_declaration():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == __version__


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--help"],
        ["--version"],
        ["lsp-server", "--help"],
        ["lsp-server", "--version"],
        ["validate"],
    ],
)
def test_non_server_commands_and_server_help_do_not_load_server_dependencies(arguments, tmp_path):
    script = """import sys
class BlockServerImports:
    def find_spec(self, fullname, path=None, target=None):
        blocked = fullname.split('.')[0] in {'pygls', 'lsprotocol'}
        if blocked or fullname.startswith('aa2modulus.lsp'):
            raise AssertionError('unexpected server import: ' + fullname)
sys.meta_path.insert(0, BlockServerImports())
from aa2modulus.cli.main import main
raise SystemExit(main(sys.argv[1:]))
"""
    source = tmp_path / "ordinary.aa2m"
    source.write_text('module "Ordinary" {}', encoding="utf-8")
    if arguments == ["validate"]:
        arguments.append(str(source))
    result = subprocess.run(
        [sys.executable, "-c", script, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (2 if not arguments else 0), result.stderr
    if "--version" in arguments:
        assert result.stdout == f"aa2modulus {__version__}\n"
    if "--help" in arguments:
        assert "stdio" in result.stdout
        assert "--tcp" not in result.stdout
