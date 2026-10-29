---
description: Give a repeated value one name with const; the compiled module stays identical.
---

# Constants

Naive writes the storage key `"Naive"` four times. A typo in one of them
would make that trigger read a different entry, and nothing would warn you.
A constant gives the value one name:

```aa2m
const Flag: string = "Naive";

module "Naive" {
  description "Believes that everyone is a nice person at heart. [PC/NPC Module]";

  trigger "Init" {
    on CARD_ADDED;
    if (TriggeringCard == ThisCard) {
      ThisCard.SetBool(Flag, ThisCard.GetBool(Flag, true));
    }
  }

  trigger "a" {
    on CONVERSATION_END;
    ...
    if (ThisCard.GetBool(Flag, true)) {
      ...
    }
  }
  ...
}
```

This compiles to exactly the same bytes as the original Naive. The compiler
puts the value in wherever the name is used, and the constant itself never
reaches the game. A misspelled `Flgs` is now an unknown name, and the
compiler stops on it.

A constant needs a type (`int`, `float`, `bool` or `string`) and a plain
value. It can't be calculated, but it can be another constant:

```aa2m
const Flag: string = "Naive";
const LegacyFlag: string = Flag;
```

## Where to put them

A constant at the top of the file, outside the module, can be used anywhere in
the file, including in [macros](macros-and-libraries.md) and
[trigger templates](trigger-templates.md). A constant inside the module is
visible only in that module.

## Constants or globals

Use a constant for a value you as the author choose and never want changed,
like a storage key. Use a global for a value players might want to change in
AA2Edit.exe, like Observer's hotkey. A global is saved on the card and costs a
variable in the game. A constant costs nothing.

A global can start from a constant:

```aa2m
const DefaultKey: int = 81;

module "Observer" {
  global OBS_KEY: int = DefaultKey;
  ...
}
```

Next: [Macros and libraries](macros-and-libraries.md).
