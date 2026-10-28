---
description: Keep several modules in one folder with shared libraries, and know what modules can and can't share in the game.
---

# Several modules

Once you have more than one module, keep them in one folder with their shared
libraries next to them:

```text
my-modules/
  naive.aa2m
  tutor.aa2m
  libraries/
    flags.aa2mi
    study.aa2mi
  build/
```

Each `.aa2m` file is one module, and you compile each one on its own:

```bash
aa2modulus compile naive.aa2m -o build/Naive
aa2modulus compile tutor.aa2m -o build/Tutor
```

A library can be imported by any number of modules. Change it and recompile
the modules that import it, since each compiled module carries its own copy of
what it used.

In VS Code, the editor checks every open file as you type, including the
libraries they import. Rename a macro or constant in a library with F2 and the
editor updates the modules that use it.

## What modules share in the game

Each compiled module stands alone. In the game, modules on the same card or
in the same class share only storage:

- Card storage entries are shared by every module on that card. Naive's flag
  is just a `Naive` entry, so Tutor could read
  `ThisCard.GetBool("Naive", false)` to find out whether its card also has
  Naive.
- Class storage entries are shared by every module in the class.
- Globals are not shared. A module only sees the globals it declares.

Pick storage keys that won't collide with other modules. A key holds one type
of value, and two modules using the same key for different things will break
each other.

A module can list other modules with `depends_on "Name";`. That's only a note
stored in the file. It doesn't load the other module or give access to its
globals.

Next: [Trigger templates](trigger-templates.md).
