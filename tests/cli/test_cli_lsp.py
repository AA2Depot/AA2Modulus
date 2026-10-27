"""Server dispatch preserves dependency-free help and ordinary CLI workflows."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib

from aa2modulus.version import __version__
from tests.support.paths import ROOT

# A fresh interpreter that refuses server imports, then runs each argument list in turn.
SCRIPT = """import contextlib, io, json, sys
class BlockServerImports:
    def find_spec(self, fullname, path=None, target=None):
        blocked = fullname.split('.')[0] in {'pygls', 'lsprotocol'}
        if blocked or fullname.startswith('aa2modulus.lsp'):
            raise AssertionError('unexpected server import: ' + fullname)
sys.meta_path.insert(0, BlockServerImports())
from aa2modulus.cli.main import main
results = []
for arguments in json.loads(sys.argv[1]):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(arguments)
        except SystemExit as exit_info:
            code = exit_info.code
    results.append({"code": code, "stdout": out.getvalue(), "stderr": err.getvalue()})
print(json.dumps(results))
"""


def test_version_matches_project_declaration():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == __version__


def test_non_server_commands_and_server_help_do_not_load_server_dependencies(tmp_path):
    source = tmp_path / "ordinary.aa2m"
    source.write_text('module "Ordinary" {}', encoding="utf-8")
    argument_lists = [
        [],
        ["--help"],
        ["--version"],
        ["lsp-server", "--help"],
        ["lsp-server", "--version"],
        ["validate", str(source)],
    ]

    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, json.dumps(argument_lists)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    no_arguments, help_, version, server_help, server_version, validate = json.loads(result.stdout)
    assert no_arguments["code"] == 2
    assert "usage:" in no_arguments["stderr"]
    for printed in (help_, server_help):
        assert printed["code"] == 0
        assert "stdio" in printed["stdout"]
        assert "--tcp" not in printed["stdout"]
    for printed in (version, server_version):
        assert (printed["code"], printed["stdout"]) == (0, f"aa2modulus {__version__}\n")
    assert validate["code"] == 0
