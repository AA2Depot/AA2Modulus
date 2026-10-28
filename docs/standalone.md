# Standalone executables

The standalone executable runs `inspect`, `validate`, `compile`, `decompile`,
`editor-data` and `lsp-server` with no Python installation and no AAUnlimited
checkout. The [release workflow](../.github/workflows/release.yml) builds it
on Ubuntu 24.04 x64 and Windows Server 2025 x64 runners. Earlier builds were
also checked by hand on Ubuntu 22.04 x64 and Windows 11 x64 (10.0.26100),
including a run of the Windows `.exe` from WSL2.

Everything under `dist/` is an untracked local build product. A fresh checkout
has none of it, so build first (below).

## Linux build

With the pinned development environment:

```bash
mise install
mise exec -- uv sync --locked --group build
mise run build
```

The single-file executable is `dist/linux-x64/aa2modulus`. Try it:

```bash
./dist/linux-x64/aa2modulus --help
./dist/linux-x64/aa2modulus validate examples/notification.aa2m
./dist/linux-x64/aa2modulus lsp-server --version
```

## Windows build

Use native Windows 10 or later, x64, with Python 3.13.15 and uv 0.12.15 to
match [mise.toml](../mise.toml). `mise run build` works there too. Without
mise, run this from the checkout in PowerShell:

```powershell
uv sync --locked --group build --python 3.13.15
uv run --locked --group build python tools/build.py
.\dist\windows-x64\aa2modulus.exe --help
.\dist\windows-x64\aa2modulus.exe validate examples\notification.aa2m
.\dist\windows-x64\aa2modulus.exe lsp-server --version
```

The builder checks the executable before it writes the notices and hashes.
To compare the executable with `SHA256SUMS`:

```powershell
Get-FileHash .\dist\windows-x64\aa2modulus.exe -Algorithm SHA256
Get-Content .\dist\windows-x64\SHA256SUMS
```

WSL2 can run the Windows executable directly. Give it Windows paths and file
URIs.

## Recipe and outputs

[The build script](../tools/build.py) uses the locked PyInstaller 6.22.3 from
the separate `build` dependency group. It builds one single-file console
executable and then checks it. Its helpers live in
[tools/standalone/](../tools/standalone/). Each output directory holds:

| Output | Purpose |
| --- | --- |
| `aa2modulus` / `aa2modulus.exe` | The single-file executable to copy and run |
| `LICENSE.txt` | The project's license, GPL-3.0-only |
| `THIRD_PARTY_NOTICES.txt` | Full license texts of the Python and runtime distributions in the build, including the PyInstaller bootloader exception |
| `SHA256SUMS` | SHA-256 of the executable |
| `README.txt` | Toolchain version, license, source code URL and launch instructions |

The default output directory is `dist/<target>`. A new build first deletes
these five files and leaves anything else in the directory alone. To keep an
earlier build, choose another path:

```bash
uv run --locked --group build python tools/build.py --output dist/recheck
```

Point the editor at the executable in that directory. If the check fails, the
executable stays in the output directory without notices or hashes; fix the
problem and build again. Build on each target OS, because PyInstaller does not
cross-compile. A single-file executable unpacks its resources to a temporary
folder at startup; see
[PyInstaller's operating modes](https://pyinstaller.org/en/stable/operating-mode.html).

## Verification and editor launch

[The verifier](../tools/standalone/verify.py) is a smoke check: `--version`
and `lsp-server --version` must exit 0, write nothing to stderr and print the
source version. The test suite covers behaviour before the build.

To launch the server from an editor, configure the absolute path of the
executable with the arguments `["lsp-server"]`. The frozen executable needs no
working directory or `PYTHONPATH`. [LSP setup](lsp.md) describes language IDs
and behaviour.

Pushing a `v*.*.*` tag runs the release workflow. Each build job runs
`mise run verify`, builds, and runs its own executable's `editor-data
manifest`. [tools/release_manifest.py](../tools/release_manifest.py) requires
the two fragments to match and publishes them as `aa2modulus-manifest.json`
next to the zips (see the [client contract](lsp.md#client-contract)).

The artifacts are unsigned. Hashes identify the files that were built; the
locked inputs do not make builds byte-for-byte reproducible. Running modules
inside the game itself has not been tested.
