---
description: Modules, descriptions, dependencies, globals, triggers and events.
---

# Modules and triggers

```aa2m
module "Observer" {
  description "Prevents NPCs from interacting with you.";
  global OBS_KEY: int = 81;

  trigger "OnKeyPress" {
    on KEY_PRESS;
    ...
  }
}
```

A `.aa2m` file has exactly one module. Its name is the name AA2Edit shows on
a card, whatever the compiled file is called. Inside it, in any order:

| Item | Meaning |
| --- | --- |
| `description "...";` | The module's description. |
| `depends_on "Name";` | A note naming another module. |
| `global name: type = value;` | A variable every trigger can use. |
| `const Name: type = value;` | A [constant](constants.md) for this module. |
| `trigger "Name" { ... }` | A trigger. |
| `import.trigger "Name" { ... }` | A trigger from a [template](libraries.md#trigger-templates). |

## Description

A one-line description is a string. A longer one can be a block string that
starts and ends with `"""`:

```aa2m
description """
  Observer : Prevents NPCs from interacting with you.

  [PC Only]
  """;
```

The closing `"""` goes on its own line, and its indentation is removed from
every line above it. The usual string escapes work inside.

## Dependencies

`depends_on "Other Module";` stores another module's name in the compiled
file. That's all it does. It doesn't load the module, make its globals
visible or import anything from it. Most modules have none.

## Globals

```aa2m
global PacifistOpponent: card = 25;
```

A global belongs to the module, and every trigger can read and assign it. The
value is saved on the card, and players can change it in AA2Edit.exe. If a
card already has a global with the same name when the module is added, the
game keeps the card's value.

The starting value must be a plain value or a constant. A few decompiled
modules have globals whose saved value differs from their starting value. The
decompiler writes those in a longer form, which you can use too:

```aa2m
global counter: int {
  default 0;
  current 1;
  initialized true;
}
```

A module can't use globals another module declares, even on the same card.
Use card storage or class storage to share values between modules.

## Triggers

```aa2m
trigger "Init" {
  on CARD_ADDED;
  let race: string = "Human ";
  if (TriggeringCard == ThisCard) {
    ThisCard.SetString("Race", race + ThisCard.GetString("Race", ""));
  }
}
```

A trigger holds events, local variables and statements. Every trigger in a
module needs a different name.

## Events

`on EVENT;` makes the trigger run when the event happens. A trigger can list
several and runs for any of them:

```aa2m
on CARD_INITIALIZED;
on CARD_ADDED;
```

A trigger with no events never runs on its own. The
[built-ins reference](../reference/builtins/index.md) lists every event.

`ThisCard` is the card the module is installed on. `TriggeringCard` is the
card the event is about, and many events fill in more values under
`Context`. The [tour](../tour/this-card.md) explains why most triggers compare
the two.

## Local variables

```aa2m
let coach: card = 25;
```

A local belongs to one trigger. You can declare it anywhere in the trigger,
and it's visible in the whole trigger, including above its declaration.
Blocks like `if` don't start a new scope, so two locals in one trigger can't
share a name.
