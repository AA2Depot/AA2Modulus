# Development

Run every command from the repository root. [mise.toml](../mise.toml) pins
Python and uv, and [uv.lock](../uv.lock) records the dependencies.
`mise run setup` prepares the environment. The project sets `package = false`
on purpose: it ships only as a standalone executable, built with a separate
dependency group and the [native build recipe](standalone.md).

## Checks

| Command | What it does |
| --- | --- |
| `mise run setup` | Installs the locked dependencies into `.venv` |
| `mise run format` | Formats the package, tests and tools with Ruff |
| `mise run lint` | Runs Ruff lint, the Ruff format check, mypy and the layer check |
| `mise run test` | Runs the test suite in parallel. Extra arguments go to pytest; `-n 0` runs it serially |
| `mise run coverage` | Runs the suite with branch coverage and an 85% floor |
| `mise run verify` | Runs `lint` and `test`. Run it before you hand over work |
| `mise run docs:serve` / `docs:build` | Previews or builds the documentation website |
| `mise run docs:builtins` | Regenerates the built-ins pages from the editor catalog; add `--check` to compare only |
| `mise run registry --source-root <dir>` | Regenerates the registry from a pinned source checkout; add `--check` to compare only |
| `mise run build` | Builds and verifies the native single-file executable (`tools/build.py`) |

To run part of the suite, pass pytest arguments to `test`. Every test carries
the marker of its area:

| Command | Area |
| --- | --- |
| `mise run test -m source` | Authoring, imports, macros, templates, diagnostics and source limits |
| `mise run test -m binary` | Native compatibility, recovery, codecs, validation and wire limits |
| `mise run test -m metadata` | Shipped spellings, policy effects and resource-loading diagnostics |
| `mise run test -m cli` | Commands, inspection, streams, exit codes, file preservation and runtime isolation |
| `mise run test -m lsp` | Stdio sessions, authoring, document edits, ranges and URIs |

`mise run test tests/cli/test_runtime_independence.py` runs the CLI from a
copy that holds only runtime code, resources and inputs, with reads from the
original project blocked.

Coverage also traces the CLI and LSP child processes that tests start
(`patch = ["subprocess"]`). That makes `mise run coverage` about twice as
slow as `mise run test`.

Every push runs [the CI workflow](../.github/workflows/ci.yml): `lint`, plus
`test` on every other branch and `coverage` instead on `main`. The `main` run
also writes the README coverage badge to `coverage.json` on the orphan
`badges` branch.

`mise run docs:builtins` regenerates `docs/reference/builtins/` (see
[built-ins pages](metadata.md#built-ins-pages)). It is not part of `lint` or
`test`, and no test checks the built-ins pages.

`editor-data` prints the JSON documents editor clients and tools read:

- `editor-data catalog` prints the built-ins catalog (schema
  `aa2modulus.editor-builtins.v1`) with compile-checked examples. The server
  renders its `aa2m-builtin:` pages from the same entries, and
  `mise run docs:builtins` renders the website's pages from them. No client
  needs the file itself.
- `editor-data lexicon` prints the lexicon and syntax fingerprint the server
  advertises. The extension's `npm run test:server` check runs it against the
  executable under test and compares it with the extension's TextMate grammar.
- `editor-data manifest` prints the compatibility facts of the
  [release manifest](lsp.md#client-contract). The release workflow runs it on
  each built executable.

```bash
aa2modulus editor-data catalog --output <scratch>/catalog.json
aa2modulus editor-data lexicon --output <scratch>/lexicon.json
aa2modulus editor-data manifest
```

Tests live in five directories under [tests/](../tests/): `source`, `binary`,
`metadata`, `cli` and `lsp`. The directory gives each test its marker, and
collection fails on a test module outside them. Shared helpers live in
[tests/support/](../tests/support/). Where the native fixtures came from is
recorded next to the
[native binaries](https://github.com/AA2Depot/AA2Modulus/blob/main/tests/fixtures/modules/README.md).

For a focused edit, run the affected directory or module and the quality
checks that apply. `lint`, `test` and `coverage` need no AAUnlimited checkout.
Registry regeneration is occasional manual maintenance and no check runs it.
The files in `examples/` are illustrations for users; the only test that reads
them is the LSP workspace-symbol test, which indexes the folder. The suite
does not test the developer tools or the VS Code extension.

Ruff lint and formatting cover runtime code, tests and tools, with the rule
set in [pyproject.toml](../pyproject.toml). Mypy checks runtime code and tools
in strict mode. Lark's untyped `InteractiveParser` API is the one call target
excluded from the untyped-call check. The ordinary checks do not install the
`build` dependency group. [Code style](style.md) covers the conventions the
tools cannot check.

`tools/check_layers.py` runs as part of `lint`. It assigns every `aa2modulus`
module a layer, so each package imports only from its own layer or lower ones.
It fails on:

- an import from a higher layer,
- an `aa2modulus` import inside a function or class,
- an import of another module's `_private` name,
- an import-time cycle.

Its `ALLOWED` list holds the one tolerated finding: the CLI's lazy
`cli.main -> lsp.server.run` import, which keeps pygls out of CLI startup. An
`ALLOWED` entry that no longer matches anything is an error. Modules over 600
lines are reported as notes.

## What the suite protects

The product is a standalone executable with CLI and LSP interfaces. The tests
call compilation and decompilation in-process because that is fast; those
entry points are not a supported Python API.

- Assert observable results: native IDs, operand order, GUI trees, exact
  bytes, recovered source, diagnostic locations, command output and exit
  codes, and editor replies.
- Use expectations written by hand and original native binaries. Hashes pin
  the inputs. A snapshot produced by the decoder is no evidence that the
  decoder is right. Never refresh expected results to hide a failure.
- Exercise canonical spellings by compiling and recovering source, rather than
  repeating constructor and validator checks derived from the registry.
- Keep a focused edge test where a scenario cannot show safety or fidelity
  efficiently: allocation limits, binary32 bits, UTF-16, URI and position
  conversion, editor recovery and worker races. Skip redundant tests of
  helpers and dataclasses.
- Native execution in the game (Windows, MSVC) and acceptance in a real editor
  are separate evidence. The native build runs its own executable check
  ([standalone builds](standalone.md)), and the extension has its own npm
  tasks.

## Developer tools

The VS Code extension lives in its own repository,
[`aa2modulus-vscode`](https://github.com/AA2Depot/aa2modulus-vscode), with its own npm tasks and checks.

Facts derived from the AAUnlimited source are regenerated only on purpose:

```bash
mise run registry --source-root <dir>
```

`<dir>` must be an existing directory with a clean AAUnlimited checkout at the
pinned revision. The command reads it without changing it and updates
`aa2modulus/metadata/registry/`. Runtime operations never read the checkout.
[Metadata](metadata.md) explains which facts are generated and which language
choices live in the editable policy.

With `--check`, the command regenerates in memory and reports missing, stale
and extra registry files without writing anything. Both modes validate the
generated files with the runtime loader. Facts that need judgment are never
generated; they belong in the language policy.

## Version

`aa2modulus/version.py` holds the toolchain version. `aa2modulus --version`,
`lsp-server --version`, the LSP `serverInfo.version` and the standalone
`README.txt` all report it. Change it together with `[project].version` in
`pyproject.toml`; `tests/cli/test_cli_lsp.py` fails when the two differ.
There is no build identity, so every build of one version reports the same
text.

### Release checklist

1. Run `uv version X.Y.Z`. It updates `pyproject.toml` and `uv.lock`.
2. Set `__version__` in `aa2modulus/version.py` to the same value.
3. Run `mise run verify`.
4. Merge the release commit into `main`.
5. Tag `main` and push the tag: `git tag vX.Y.Z` and `git push origin vX.Y.Z`.
   The [release workflow](../.github/workflows/release.yml) refuses a tag
   that differs from the project version.
6. When the workflow finishes, check that the release has both zips and
   `aa2modulus-manifest.json`. Add the breaking wire changes to the generated
   notes, and mark the release as a pre-release if it is one.

## Project records

Contributor rules, the work-log format, plans and handover are in
[AGENTS.md](https://github.com/AA2Depot/AA2Modulus/blob/main/AGENTS.md).
