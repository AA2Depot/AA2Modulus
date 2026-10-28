---
description: Library files, imports and trigger templates with slots.
---

# Libraries and templates

A library is a `.aa2mi` file with imports, macros, constants and trigger
templates, but no module. Libraries let several modules share code.

## Imports

```aa2m
import "libraries/study.aa2mi";
```

Imports go outside the module, before or after it. The path ends in `.aa2mi`
and is relative to the file that has the `import`. Use `/` between folders so
the path works on Windows and Linux. A library can import other libraries.

Everything a module imports, directly or not, shares one set of names. Two
macros, templates or constants with the same name are an error, even in
different files. Importing the same library twice, by two routes, is fine.
Libraries can't import each other in a circle.

Imports only exist in the source. The compiled module contains the expanded
actions and doesn't need the library in the game. `depends_on` is unrelated
and imports nothing.

## Trigger templates

A trigger template is a trigger in a library with `slot` declarations at the
top. A slot is a typed value the module fills in:

```aa2m
trigger "Init" {
  slot flag string;
  on CARD_ADDED;
  if (TriggeringCard == ThisCard) {
    ThisCard.SetBool(flag, ThisCard.GetBool(flag, true));
  }
}
```

A module uses it with `import.trigger`, which puts the trigger where the line
is:

```aa2m
import "libraries/flags.aa2mi";

module "Naive" {
  import.trigger "Init" {
    slot flag = "Naive";
  }
}
```

The braces are required even when the template has no slots, and there's no
`;` after them. The trigger keeps the template's name unless you give it
another one: `import.trigger "Init" "Setup" { ... }`. A module can use a
template several times with different names, and every trigger in the module
needs a different name.

Every slot has to be filled, and slot types are `card`, `int`, `float`,
`bool` or `string`. As with macros, a slot's value is copied to every place
the slot is used.

## What a template can use

A template sees its slots, its own `let` variables, the game's built-ins,
macros and constants declared outside any module. It can't see the module's
globals or constants, so pass those in through slots. The module's values in
a slot can use the module's globals and constants.

If a template's local variable has the same name as one of the module's
globals, the compiler renames the local to `_aa2m_local_0` (or the next free
number) in that trigger. Otherwise the global would win, as it does for any
local.

Unused templates are checked but add nothing to the compiled module.
