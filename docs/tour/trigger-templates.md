---
description: Share a whole trigger between modules with a trigger template and typed slots.
---

# Trigger templates

Naive and Tutor both have this `Init` trigger, with only the storage key
changed:

```aa2m
trigger "Init" {
  on CARD_ADDED;
  if (TriggeringCard == ThisCard) {
    ThisCard.SetBool("Naive", ThisCard.GetBool("Naive", true));
  }
}
```

A macro can't hold it, because a macro is a block of actions and this is a
whole trigger with its own event. A trigger template can.

## Writing a template

Templates live in libraries. `libraries/flags.aa2mi`:

```aa2m
// Marks the card that has the module, once it joins the class.
trigger "Init" {
  slot flag string;
  on CARD_ADDED;
  if (TriggeringCard == ThisCard) {
    ThisCard.SetBool(flag, ThisCard.GetBool(flag, true));
  }
}
```

A template looks like a trigger with `slot` lines at the top. A slot is a
typed value the module fills in, here the storage key.

## Using it

In the module, `import.trigger` puts the template's trigger where the line is:

```aa2m
import "libraries/flags.aa2mi";

module "Naive" {
  description "Believes that everyone is a nice person at heart. [PC/NPC Module]";

  import.trigger "Init" {
    slot flag = "Naive";
  }

  trigger "a" {
    ...
  }
}
```

Tutor does the same with `slot flag = "Tutor";`. Both modules still compile to
exactly the same bytes as the originals: the template becomes an ordinary
trigger named `Init`.

To give the trigger a different name in the module, add it after the template
name: `import.trigger "Init" "Setup" { ... }`. A module can use the same
template more than once with different names.

## What a template can see

A template sees only its slots, its own `let` variables, the game's built-ins
and constants declared outside any module. It can't see the module's globals,
so pass anything it needs through a slot. Every slot has to be filled in.

That's the end of the tour. The [language section](../language/index.md)
covers each feature in full, and the
[built-ins reference](../reference/builtins/index.md) lists everything you
can call.
