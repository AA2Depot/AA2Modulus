---
description: Decompile and inspect modules made in AA2Edit, and what the decompiler does with unusual ones.
---

# Working with existing modules

Any module made in AA2Edit can be turned into source, changed and compiled
again. This page covers what to expect when you do.

## Decompile

```bash
aa2modulus decompile "Tutor" -o tutor.aa2m
```

Without `-o` the source goes to the terminal. In VS Code, run
**AA2M: Decompile Module**.

The source compiles back to the same bytes as the file you started with. The
exceptions are two kinds of damage the game ignores anyway: bytes left over
after the end of the module, which the decompiler reports as a
`TRAILING_BYTES` warning, and odd values in true/false fields, which it reads
as `true`.

Comments, macros, constants and library imports don't exist in a compiled
module, so a decompiled module never has them. You get the expanded actions.

## Warnings in decompiled source

The decompiler reports problems in the source it writes, with line numbers
pointing into that source. The common ones:

`UNDEFINED_VARIABLE`
:   The module reads a global it never declares, usually one another module on
    the card declares. aa2modulus only lets a module use its own globals, so
    the help line gives you the declaration to add, such as
    `global counter: int = 0;`. Adding it is safe: if the card already has a
    global with that name, the game keeps the card's value. The compiled
    module then has one more global and is no longer byte-identical.

`RAW_FALLBACK`
:   Something in the module has no readable form, for example an ID the
    toolchain doesn't know, so it's written as a raw record:
    `raw_action 9002(...)` or `raw_expression int 3 { ... }`. A raw record
    with a known ID compiles back exactly. One with an unknown ID doesn't
    compile. [Raw forms](../language/raw-forms.md) has the details.

`NATIVE_HAZARD_ALLOWED`
:   The module relies on a known AAUnlimited bug, so the decompiler put an
    `@allow(...)` line in front of it. Without that line the module wouldn't
    compile. [Known AAUnlimited bugs](../language/hazards.md) explains each
    one.

A decompiled module can have errors and still be written out. `decompile`
returns success as long as it could read the file, and `validate` tells you
what to fix before it compiles.

## Inspect

```bash
aa2modulus inspect "Tutor"
```

`inspect` prints the module's records the way AA2Edit shows them, with native
names like `If (TriggerCard == ThisCard) then`, IDs and any problems it finds.
It writes no source, so use it to compare a module with what you see in
AA2Edit. Add `--strict` to make it exit with an error when it finds one.
