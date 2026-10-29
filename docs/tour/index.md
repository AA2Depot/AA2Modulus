---
description: Learn the .aa2m language by reading and changing real AAUnlimited modules.
---

# Tour of the language

The tour teaches the language with real modules: Race-Human, Naive, Tutor,
Observer and Pacifist. They were made in AA2Edit and are kept in the
repository as test files. Each page decompiles one, explains what it does and
then changes something about it.

Some of these modules are named after personality traits, like Naive or
Pacifist. They're still modules. The traits you tick in AA2Edit's character
editor are a separate thing, and these modules don't change them.

Most changes in the tour, like a constant, a macro, a library or a shared
trigger, compile to exactly the same bytes as the original module.

1. [A first module](first-module.md): Race-Human, line by line.
2. [ThisCard and TriggeringCard](this-card.md): why almost every trigger
   starts with the same check.
3. [Reacting to the game](game-events.md): Naive, with conversation events,
   variables and arithmetic.
4. [Keeping state](state.md): Observer and Pacifist, with globals, storage
   and loops.
5. [Constants](constants.md): name a value once.
6. [Macros and libraries](macros-and-libraries.md): reuse a block of actions
   in Tutor, then move it to its own file.
7. [Several modules](several-modules.md): keep Naive and Tutor side by side
   with a shared library.
8. [Trigger templates](trigger-templates.md): share the `Init` trigger both
   modules have.

You'll need the compiler or the VS Code extension from
[Get started](../quickstart.md) to follow along.
