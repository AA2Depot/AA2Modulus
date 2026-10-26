# aa2modulus

[![CI](https://github.com/AA2Depot/AA2Modulus/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AA2Depot/AA2Modulus/actions/workflows/ci.yml?query=branch%3Amain)
[![Coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FAA2Depot%2FAA2Modulus%2Fbadges%2Fcoverage.json)](https://github.com/AA2Depot/AA2Modulus/actions/workflows/ci.yml?query=branch%3Amain)
[![License](https://img.shields.io/github/license/AA2Depot/AA2Modulus)](LICENSE)

If you've ever built an AAUnlimited trigger module in AAEdit, you know the
drill: lots of clicking, nested menus, and no easy way to see the whole thing
at once. aa2modulus lets you write those modules as plain text instead, compile
them to the exact binary format AAUnlimited reads, and turn existing modules
back into readable source.

> [!NOTE]
> **AI disclaimer:** a good chunk of this code was written with AI assistance.
> I reviewed it as it went in and fixed it wherever it fell short, so nothing
> here got merged blindly. Honestly, the codebase is big enough that I couldn't
> have built all of these features (or tests this thorough) on my own.

## What it looks like

Here's a whole module. It shows a notification every time a card gets added
to the class:

```aa2m
module "Notification Example" {
  description "Show a notification when a card is added to class";

  trigger "On Card Added" {
    on CARD_ADDED;
    Notification(ThisCard.FullName + " has been added to class");
  }
}
```

That's it. A module holds triggers, each trigger says which events start it
(`on ...`) and which actions it runs. On top of that you get typed variables,
`if`/`else` and loops, constants, macros and `.aa2mi` libraries you can import
(the [examples](examples/) folder shows most of these).

## What it does

One executable, six commands:

- `validate` checks a module and tells you exactly where it's wrong
- `compile` turns `.aa2m` source into a binary module
- `decompile` turns a binary module back into source, usually one that
  compiles to the exact same bytes
- `inspect` prints a binary module's records as AAUnlimited sees them
- `lsp-server` runs the language server for your editor
- `editor-data` prints the built-ins catalog, lexicon or release manifest your editor extension reads

`aa2modulus <command> --help` lists the options, and
[CLI usage](docs/user/cli-usage.md) covers all of them plus the exit codes.

## Getting started

No releases yet.
TODO: Need to expand on this.

## Editor support

`aa2modulus lsp-server` speaks the Language Server Protocol over stdio, so any
editor with an LSP client can use it. You get diagnostics as you type,
completion, hover, go to definition, rename and a few more. There's also a
VS Code extension, which lives in its own repository (`aa2modulus-extension`).
Setup for other editors is in [language server](docs/lsp.md).

## Docs

- [Get started](docs/quickstart.md), the same thing as above but slower
- [Language reference](docs/language.md), everything you can write
- [Grammar](docs/grammar.md), if you want the exact syntax
- [Metadata](docs/metadata.md), names, defaults and the language policy
- [Native format](docs/native-format.md), the binary layout and where each fact comes from

## Development

The project is written with Python 3.13. You only need two things installed
yourself: [git](https://git-scm.com/) and [mise](https://mise.jdx.dev/)
(version 2026.9.7 or newer). mise pulls in the pinned Python and
[uv](https://docs.astral.sh/uv/) for you, and uv installs the locked
dependencies into `.venv`.

```bash
git clone https://github.com/AA2Depot/AA2Modulus.git
cd AA2Modulus
mise trust       # mise won't read mise.toml from a fresh clone until you trust it
mise install     # Python and uv
mise run setup   # the locked dependencies
```

From there, everything you need to run goes through mise:

```bash
mise run test    # the test suite
mise run verify  # lint, types, layer check and tests, run this before you hand anything in
```

`mise tasks` lists the rest.

Before you touch the code, read [architecture](docs/architecture.md) for where
things live, [development](docs/development.md) for the rest of the tasks and
[code style](docs/style.md) so your code looks like the rest of it.

If you're an AI agent, [AGENTS.md](AGENTS.md) is for you.

## License

aa2modulus is licensed under the [GNU General Public License v3.0 only](LICENSE)
(`GPL-3.0-only`). You're free to use, change and share it, but anything you
distribute that's built on it has to use the same license and come with its
source.

Copyright (C) 2026 R00taryEnginE
