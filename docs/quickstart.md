# Get started

This page takes you from nothing to a compiled AAUnlimited trigger module with
the standalone `aa2modulus` executable. You need no Python installation.

## Get the executable

There are no published releases yet. Build the executable from a checkout
([standalone builds](standalone.md)):

```bash
mise run build
```

The result is `dist/linux-x64/aa2modulus` on Linux or
`dist\windows-x64\aa2modulus.exe` on Windows. Copy it anywhere, or put its
folder on your `PATH`. Check it runs:

```bash
aa2modulus --version
```

## Write a module

Save this as `hello.aa2m`:

```aa2m
module "Hello" {
  trigger "Greet" {
    on CARD_ADDED;
    Notification("Hello from aa2modulus");
  }
}
```

A module holds triggers. Each trigger lists the events that start it (`on ...`)
and the actions it runs. The [language reference](language.md) covers the rest.

## Check and compile it

```bash
aa2modulus validate hello.aa2m
aa2modulus compile hello.aa2m -o Hello
```

`validate` reports problems without writing anything. `compile` writes the
binary module `Hello`. AAUnlimited module files have no extension. Put the file
in the AAUnlimited `module` override folder, where AAEdit lists it.

A mistake gives a located error:

```text
error[UNKNOWN_ACTION_NAME]: no unique action 'Notifcation'
 --> hello.aa2m:4:5
  |
4 |     Notifcation("Hello from aa2modulus");
  |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

The [diagnostic reference](reference/diagnostics.md) explains each code.

## Read an existing module

```bash
aa2modulus decompile Hello -o recovered.aa2m
aa2modulus inspect Hello
```

`decompile` turns a binary module back into source that compiles to the same
bytes. `inspect` prints the module's records without writing anything.

## Next steps

- [CLI usage](user/cli-usage.md): every command, option and exit code.
- [Language server](lsp.md): editor support over `aa2modulus lsp-server`.
- The repository's `examples/` folder: modules that use constants, macros,
  libraries and receiver calls.
