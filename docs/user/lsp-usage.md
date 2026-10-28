---
description: Use the aa2modulus language server in any editor with an LSP client.
---

# Other editors

`aa2modulus lsp-server` is a language server that talks over stdin and
stdout. Any editor with an LSP client can use it, and it gives the same
results as the [VS Code extension](vscode-extension.md): errors as you type,
completion, hover, signature help, go to definition, find references, rename,
semantic colors, inlay hints and quick fixes.

## Setting it up

Your editor needs three things:

- The command: the full path to `aa2modulus` (`aa2modulus.exe` on Windows)
  with the argument `lsp-server`. It works from any folder.
- The file types: `.aa2m` for modules and `.aa2mi` for libraries.
- The language ID: `aa2m` for modules. Libraries can use `aa2m` or `aa2mi`.

The examples below assume `aa2modulus` is on your `PATH`. Check your editor's
LSP documentation for the details of its version.

Neovim 0.11 or newer, in `init.lua`:

```lua
vim.filetype.add({ extension = { aa2m = "aa2m", aa2mi = "aa2mi" } })
vim.lsp.config("aa2modulus", {
  cmd = { "aa2modulus", "lsp-server" },
  filetypes = { "aa2m", "aa2mi" },
  root_markers = { ".git" },
})
vim.lsp.enable("aa2modulus")
```

Helix, in `languages.toml`:

```toml
[language-server.aa2modulus]
command = "aa2modulus"
args = ["lsp-server"]

[[language]]
name = "aa2m"
scope = "source.aa2m"
file-types = ["aa2m", "aa2mi"]
language-servers = ["aa2modulus"]
```

## Good to know

- The server checks the files you open, and the libraries they import. A
  file you never opened gets no errors, though find references and rename
  still search it.
- Compile and decompile are LSP commands the VS Code extension calls. In
  another editor, run the [command line](cli-usage.md) instead.
- F12 on a built-in opens its documentation page only in editors that support
  `workspace/textDocumentContent`. Hover works everywhere.
- There's no formatting.

The server's side of the protocol, for people writing an editor extension,
is in [Language server protocol](../lsp.md).
