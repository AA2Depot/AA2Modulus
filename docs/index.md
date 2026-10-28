---
description: Write AAUnlimited trigger modules as text, compile them to the binary format AAUnlimited loads, and decompile existing modules back to source.
---

# AA2 Modulus

aa2modulus is a compiler for AAUnlimited trigger modules. You write a module
as a plain text `.aa2m` file and aa2modulus turns it into the binary file that
AAUnlimited loads. It also works in reverse: give it a module made in AAEdit
and you get source back that you can read, change and compile again.

Here is a complete module. It shows a notification each time a card is added
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

A module holds triggers. Each trigger names the events that start it
(`on ...`) and the actions it runs. Beyond that you get typed variables,
`if`/`else` and loops, constants, macros and libraries you can import.

## What you can do with it

- Keep your modules as text files, in any editor and under version control.
- Find mistakes before the game does. Every error names the file, line and
  column, and most come with a hint on how to fix it.
- Open any existing module as source. Decompiled source usually compiles back
  to the exact same bytes.
- Get completion, hover, go to definition and rename in your editor through
  the language server.

## Install

The easiest way to start is the [VS Code extension](user/vscode-extension.md),
which downloads the compiler for you. For the command line, download the zip
for your system from the
[releases page](https://github.com/AA2Depot/AA2Modulus/releases) and unzip it
anywhere. There is one build for Windows x64 and one for Linux x64. The
executable runs on its own, so you don't need Python or anything else
installed.

Releases are pre-releases until version 1.0.0, and the language can still
change between them.

## Next steps

<div class="grid cards" markdown>

-   __Get started__

    ---

    Install the tools, compile your first module and load it in the game.

    [Get started](quickstart.md)

-   __Tour__

    ---

    Learn the language from real modules, one feature at a time.

    [Take the tour](tour/index.md)

-   __Language__

    ---

    Everything you can write in a `.aa2m` module or `.aa2mi` library.

    [Language basics](language/index.md)

-   __Built-ins__

    ---

    Every event, action, value and named constant from the game.

    [Built-ins](reference/builtins/index.md)

</div>

## License

aa2modulus is free software under the
[GNU General Public License v3.0 only](https://github.com/AA2Depot/AA2Modulus/blob/main/LICENSE).
The source is on [GitHub](https://github.com/AA2Depot/AA2Modulus).
