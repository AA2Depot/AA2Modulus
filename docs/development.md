# Development

Run commands from the repository root. [mise.toml](../mise.toml) pins Python and
uv; [uv.lock](../uv.lock) records dependencies. `mise run setup` prepares the
source-tree environment. `package = false` remains in place; executable builds
use a separate dependency group and [native build recipe](standalone.md).

## Checks

| Command | Coverage |
| --- | --- |
| `mise run setup` | Install the locked dependencies into `.venv` |
| `mise run format` | Format the package, tests and tools with Ruff |
| `mise run lint` | Ruff lint, the Ruff format check, mypy and the layer check |
| `mise run test` | The full test suite; extra arguments go to pytest |
| `mise run coverage` | The test suite with branch coverage and the 85% floor |
| `mise run verify` | `lint` and `test`; run it before handing over work |
| `mise run docs:serve` / `docs:build` | Preview or build the documentation website |
| `mise run registry --source-root <dir>` | Regenerate the registry from a pinned source checkout; add `--check` to compare only |
| `mise run build` | Native single-file build and verification (`tools/build.py`) |

Pass pytest arguments to `test` to run part of the suite. Each test carries one
area marker:

| Command | Area |
| --- | --- |
| `mise run test -m source` | Authoring, imports, macros, templates, diagnostics, and source limits |
| `mise run test -m binary` | Native compatibility, recovery, codecs, validation, and wire limits |
| `mise run test -m metadata` | Shipped spellings, policy effects, and resource-loading diagnostics |
| `mise run test -m cli` | Commands, inspection, streams, exits, file preservation, and runtime isolation |
| `mise run test -m lsp` | Stdio sessions, authoring, document edits, ranges, and URIs |

`mise run test tests/cli/test_runtime_independence.py` runs the CLI from a copy
holding only runtime code, resources and inputs, with original-project reads blocked.

Coverage also traces the CLI and LSP child processes the tests start
(`patch = ["subprocess"]`), which makes the coverage run about three times
slower than `mise run test`.

`tools/export_reference.py --output-dir <dir>` exports the portable reference
bundle on request; nothing in the repository keeps a copy (see
[metadata maintenance](metadata.md#portable-language-and-metadata-reference)).
These operations are outside `check`; neither examples nor reference generation
is a pytest subject.

The editor's compiled-example built-in documentation, `builtins.json`, belongs
to the extension repository. The `editor-data catalog` command writes it, so a
release executable produces the catalog that matches its own server.
`editor-data lexicon` prints the lexicon and syntax fingerprint the server
advertises, for the extension's grammar test. `editor-data manifest` prints the
compatibility facts of the [release manifest](lsp.md#client-contract):

```bash
aa2modulus editor-data catalog --output <extension>/docs/generated/builtins.json
aa2modulus editor-data catalog | diff - <extension>/docs/generated/builtins.json
aa2modulus editor-data lexicon --output <scratch>/lexicon.json
aa2modulus editor-data manifest
```

Tests live in five directories under [tests/](../tests/): `source`, `binary`,
`metadata`, `cli`, and `lsp`. Each directory supplies its one focused marker.
Collection rejects tests outside those owners. Shared helpers live in
[tests/support/](../tests/support/); fixture provenance is recorded alongside
the [native binaries](../tests/fixtures/modules/README.md).

For a focused edit, run its directory or module and the relevant quality checks.
`test`, `check`, and `coverage` require no AAUnlimited checkout. Registry
regeneration is infrequent manual maintenance, not a test gate. Examples are
unfinished user illustrations and are not automated test inputs. The Python
suite does not test developer tools or the independent VS Code extension.

Ruff lint and formatting cover runtime code, tests and development tools, with
the rule set in [pyproject.toml](../pyproject.toml). Mypy checks runtime code and
tools in strict mode; lark's untyped parser API is the one excluded call target.
Ordinary checks do not install the optional build dependency group.
Conventions the tools cannot check are in [Code style](style.md).

`tools/check_layers.py` (part of `lint`) assigns every `aa2modulus` module a layer
and fails on an import of a higher layer, an `aa2modulus` import inside a function
or class, an import of another module's `_private` name, or an import-time cycle.
Each package imports only from its own or lower layers. Its `ALLOWED` list holds
the one tolerated finding, the CLI's lazy `cli.main -> lsp.server.run` import that
keeps pygls out of CLI startup; an entry that no longer matches is an error. Modules over 600 lines are reported as notes.

## What the suite protects

The product ships as a standalone executable with CLI and LSP interfaces.
In-process compilation/decompilation entry points keep scenario tests efficient;
they do not establish a supported Python embedding API.

- Assert observable results: native IDs, operand order, GUI trees, exact bytes,
  recovered source, diagnostic locations, command streams/exits, and editor replies.
- Use hand-authored wire/source expectations and original native binaries.
  Hashes pin input integrity; decoder-generated snapshots are not independent
  evidence of decoder correctness. Do not refresh expected results to hide failures.
- Exercise canonical spellings through source compilation and recovery, rather
  than repeating registry-derived constructor and validator checks.
- Keep focused edge tests where scenarios cannot efficiently demonstrate safety
  or fidelity: allocation limits, binary32 bits, UTF-16, URI/position conversion,
  editor recovery, and worker races. Avoid redundant helper and dataclass checks.
- Native Windows/MSVC execution and real editor acceptance remain separate
  evidence. Executable verification runs during native builds
  ([standalone builds](standalone.md)); the extension has independent npm tasks.

## Developer tools

The VS Code extension lives in its own repository (`aa2modulus-extension`) with
its own tasks and checks.

Regenerate source-derived facts only as an explicit development operation:

```bash
mise run registry --source-root <dir>
```

`<dir>` must be an existing directory holding a clean AAUnlimited source
checkout at the pinned revision. The command reads it without changing it and updates
`aa2modulus/metadata/registry/`.
[Metadata editing](metadata.md) distinguishes generated facts from editable
language policy. Runtime operations never read the source checkout.

Adding `--check` regenerates into memory and reports missing, stale
and extra registry files without writing. Both modes validate the generated
files with the runtime loader. Facts that need judgment are not generated;
they live in the language policy.

## Version

`aa2modulus/version.py` holds the toolchain version. `aa2modulus --version`,
`lsp-server --version`, LSP `serverInfo.version` and the standalone `README.txt`
report it. Change it together with `[project].version` in
`pyproject.toml`; `tests/cli/test_cli_lsp.py` fails when they differ. There is
no build identity: every build of one version reports the same text.

## Project records

Contributor rules, work-log format, plans and handover are in
[AGENTS.md](../AGENTS.md); current status is the [roadmap](../plans/ROADMAP.md).
