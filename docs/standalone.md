# Standalone executables

The shared executable runs `inspect`, `validate`, `compile`, `decompile`, and
`lsp-server` without installed Python or an AAUnlimited checkout. Earlier builds
were verified on Ubuntu 22.04 x64 and Windows 11 x64 (10.0.26100), and the
Windows build was rechecked through WSL2 using native Windows Python and the
supplied `.exe` files. The current recipe has been verified on Linux x64 only. Everything under `dist/` is a local,
untracked build product: a fresh checkout has none of it and must build (below).

## Linux build

Build on Ubuntu 22.04 x64 using the pinned development environment:

```bash
mise install
mise exec -- uv sync --locked --group build
mise run build
```

The single-file executable is `dist/linux-x64/aa2modulus`. Try:

```bash
./dist/linux-x64/aa2modulus --help
./dist/linux-x64/aa2modulus validate examples/notification.aa2m
./dist/linux-x64/aa2modulus lsp-server --version
```

Other directories under `dist/` on a developer machine are earlier local builds
kept for comparison. Older builds also carry a folder bundle and JSON reports from
an earlier recipe; those reports do not prove current-source resource identity,
and the builds predate the catalog, dependency, receiver and policy work. The
[roadmap](../plans/ROADMAP.md) lists the resulting acceptance limits.

## Windows build

Use native Windows 10+ x64 with Python **3.13.15** and uv **0.12.15**, matching
[mise.toml](../mise.toml). From this checkout in PowerShell:

```powershell
uv sync --locked --group build --python 3.13.15
uv run --locked --group build python tools/build.py
.\dist\windows-x64\aa2modulus.exe --help
.\dist\windows-x64\aa2modulus.exe validate examples\notification.aa2m
.\dist\windows-x64\aa2modulus.exe lsp-server --version
```

The builder verifies the executable before writing the notices and hashes.
Compare the executable's SHA-256 with `SHA256SUMS`:

```powershell
Get-FileHash .\dist\windows-x64\aa2modulus.exe -Algorithm SHA256
Get-Content .\dist\windows-x64\SHA256SUMS
```

From WSL2, the Windows executable can run directly. Pass Windows paths and
file URIs when using it.

## Recipe and outputs

[The build script](../tools/build.py) uses locked PyInstaller 6.22.3 from the
separate `build` dependency group to build one single-file console executable,
then verifies it. Its components live in [tools/standalone/](../tools/standalone/).
Each output directory contains:

| Output | Purpose |
| --- | --- |
| `aa2modulus` / `aa2modulus.exe` | Single-file executable to copy and run |
| `LICENSE.txt` | The project's license, GPL-3.0-only |
| `THIRD_PARTY_NOTICES.txt` | Full license texts from the build's Python and runtime distributions, including the PyInstaller bootloader exception |
| `SHA256SUMS` | SHA-256 of the executable |
| `README.txt` | Toolchain version, license, source code URL and launch instructions |

The default output is `dist/<target>`. Running the build again replaces these
five files and keeps anything else in the directory. To keep an earlier build,
select another path:

```bash
uv run --locked --group build python tools/build.py --output dist/recheck
```

Configure the executable from that chosen output on the extension host
explicitly. If verification fails, the executable stays in the output directory
without notices or hashes; inspect the failure, fix it and build again. Build on each target OS; PyInstaller does not cross-compile.
Single-file startup extracts resources temporarily. See
[PyInstaller's operating modes](https://pyinstaller.org/en/stable/operating-mode.html).

## Verification and editor launch

[The verifier](../tools/standalone/verify.py) is a smoke check: `--version`
and `lsp-server --version` must exit 0, write nothing to stderr and print the
source version. Behavior is covered by the test suite before the build.

Configure an existing editor client with an absolute executable path and
`["lsp-server"]` arguments. Working directory and `PYTHONPATH` setup are unnecessary
for the frozen executable. [LSP setup](lsp.md) describes language IDs and behavior.

These are local, unsigned artifacts. Windows 10 is a build target; native
acceptance was performed on Windows 11. Hashes identify the actual outputs; locked
inputs do not establish byte-identical reproducibility. Native AAUnlimited game
execution and publication remain separate work.
