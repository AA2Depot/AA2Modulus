---
description: Install the AA2M Language extension for VS Code and use it to write, compile and decompile modules.
---

# VS Code extension

The AA2M Language extension runs the aa2modulus language server inside VS
Code. You get colors, errors as you type, completion, docs for every built-in,
and compile and decompile commands. The extension has its own repository,
[`aa2modulus-vscode`](https://github.com/AA2Depot/aa2modulus-vscode).

## Install

1. Get the latest `.vsix` from the
   [extension's releases page](https://github.com/AA2Depot/aa2modulus-vscode/releases).
2. In VS Code, open Extensions (Ctrl+Shift+X), click `…` at the top and pick
   **Install from VSIX…**.
3. Open any `.aa2m` file. When it offers to set up the server, click
   **Download Server…** and pick the newest version.

Once the server is running, the language status area (the `{}` in the status
bar) shows **AA2M: Ready**, with the server version in its details. The
download list leaves out server versions the extension can't work with and
marks old releases it can't check as "Compatibility unknown". The extension
looks for a newer server at most once a day.

If you already have `aa2modulus` somewhere, run
**AA2M: Select Server Executable…** and point it at the file.

## Writing

- Suggestions appear as you type, or with Ctrl+Space. Keywords like `trigger`
  or `if` insert a ready-made block you can Tab through.
- Mistakes get a red underline and show up in Problems (Ctrl+Shift+M). When a
  light bulb appears, Ctrl+. fixes the problem for you.
- Hover anything to see what it is. A `//` comment right above your own
  variable, constant or macro shows up in its hover.
- F12 on a built-in opens its documentation. On your own names it jumps to
  the declaration. Shift+F12 lists every use, and F2 renames it everywhere,
  libraries included.
- **AA2M: Browse Built-ins** searches every event, action and value by name
  or by what it does.

Renaming a global also renames the variable stored on the card, so other
modules on that card that read the old name won't see it any more.

## Compiling and decompiling

- **AA2M: New Module** starts a module from a template.
- **AA2M: Compile Module**, or the build button at the top right of the
  editor, compiles the module in the current editor, unsaved changes
  included, and asks where to save it. Leave the extension off the file name.
- **AA2M: Decompile Module** asks for a compiled module and opens the source
  next to it as `<file>.aa2m`.

## When something breaks

Run **AA2M: Show Language Server Output** first. It shows what the extension
tried to run and any errors.

- Nothing but comments, strings and numbers has color: the folder is
  probably in Restricted Mode. Click **Manage** in the banner and trust it.
- The server is too old, or a command is missing: download the newest
  server.
- The server stopped: click **Restart** in the notification or run
  **AA2M: Restart Language Server**.

The setting you're most likely to need is `aa2m.server.command`, the path to
the server. Downloading or selecting a server fills it in.
