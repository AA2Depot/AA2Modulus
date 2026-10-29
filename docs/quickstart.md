---
description: Install aa2modulus, write a module, compile it, load it in the game and decompile an existing one.
---

# Get started

This page takes you from nothing to a module you can add to a card in
AA2Edit.

## Download

The easiest way to work is the VS Code extension. It downloads the right
compiler for you and gives you errors as you type, completion and a compile
button.

1. Get the latest `.vsix` from the
   [extension's releases page](https://github.com/AA2Depot/aa2modulus-vscode/releases).
2. In VS Code, open Extensions (Ctrl+Shift+X), click `…` at the top and pick
   **Install from VSIX…**.
3. Open any `.aa2m` file and click **Download Server…** when it asks.

[VS Code extension](user/vscode-extension.md) covers the rest of it.

If you'd rather use the command line, download `aa2modulus-windows-x64.zip` or
`aa2modulus-linux-x64.zip` from the
[releases page](https://github.com/AA2Depot/AA2Modulus/releases) and unzip it
anywhere. It's a single executable and needs nothing else installed. Put its
folder on your `PATH`, then check that it runs:

```bash
aa2modulus --version
```

## Basic use

Modules are plain text files ending in `.aa2m`. The compiler has four commands
you'll use all the time:

| Command | What it does |
| --- | --- |
| `aa2modulus validate my-module.aa2m` | Checks the module and reports problems. Writes nothing. |
| `aa2modulus compile my-module.aa2m -o "My Module"` | Writes the binary module AAUnlimited loads. |
| `aa2modulus decompile "My Module" -o my-module.aa2m` | Turns a binary module back into source. |
| `aa2modulus inspect "My Module"` | Prints a binary module the way AA2Edit shows it. |

In VS Code the same things are commands: **AA2M: Compile Module** and
**AA2M: Decompile Module**. Errors show up as you type, so you rarely need
`validate` there.

## Your first module

This is Race-Human, a real module. Save it as `race-human.aa2m`:

```aa2m
module "Race-Human" {
  description "Is a human";

  trigger "Init" {
    on CARD_ADDED;
    let race: string = "Human ";
    if (TriggeringCard == ThisCard) {
      ThisCard.SetString("Race", race + ThisCard.GetString("Race", ""));
    }
  }
}
```

When a card joins the class, the module writes `Human` into a storage entry
called `Race` on the card that has the module. The [tour](tour/index.md) goes
through it line by line.

## Compile

```bash
aa2modulus compile race-human.aa2m -o Race-Human
```

Module files have no extension, so leave it off the output name. If something
is wrong, nothing gets written and you get an error that points at the
problem:

```text
error[UNKNOWN_MEMBER]: unknown member 'SetStrin'
 --> race-human.aa2m:8:7
  |
8 |       ThisCard.SetStrin("Race", race + ThisCard.GetString("Race", ""));
  |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

compilation failed: 1 error
```

[Diagnostic codes](reference/diagnostics.md) explains every code.

## Load it in the game

Copy the compiled file into `<game root>\data\override\module`. AAUnlimited
makes AA2Edit.exe list the modules in that folder when you edit a card. The
list shows the file name. Once you add the module to a card, the card shows
the name written in the module itself, here `Race-Human`.

## Decompile

To read a module someone else made, decompile it:

```bash
aa2modulus decompile Race-Human -o race-human.aa2m
```

You get source that compiles back to the same bytes in almost every case.
[Working with existing modules](user/existing-modules.md) explains the cases
where it can't.

## Next steps

- [The tour](tour/index.md) builds up the language with real modules.
- [Built-ins](reference/builtins/index.md) lists every event, action and value
  you can use.
- [CLI usage](user/cli-usage.md) has every command, option and exit code.
