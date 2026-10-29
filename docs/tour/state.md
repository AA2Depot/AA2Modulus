---
description: Observer and Pacifist keep state across events with globals, card storage, class storage and loops.
---

# Keeping state

A local variable is gone once its trigger finishes. To remember something
between events, a module has three places to put it: globals, card storage
and class storage.

## Globals

Observer lets the player hide from NPCs by pressing a key. The key is a
global:

```aa2m
module "Observer" {
  description "...";
  global OBS_KEY: int = 81;
  ...
}
```

A global belongs to the module and every trigger in it can read and change
it. Its value is saved on the card with the module. Once a module is out in
the wild, players can change a global's value in AA2Edit.exe without touching
the source, which is why Observer keeps the key there. 81 is the key code
for `Q`. [Key code table here](https://learn.microsoft.com/en-us/office/vba/language/reference/user-interface-help/keycode-constants#a-key---z-key).

A module only sees the globals it declares. If it reads a variable it never
declared, that's an error.

## Class storage

Card storage, which you met in [Race-Human](first-module.md), belongs to one
card. Class storage belongs to the whole class, so every module on every card
sees the same entries. Observer uses it to share one on/off switch:

```aa2m
trigger "OnKeyPress" {
  on KEY_PRESS;
  if (Context.KeyPress == ClassStorage.GetInt("OBS_KEY", 81)) {
    if (ThisCard.GetBool("Observer", false)) {
      if (ClassStorage.GetBool("ObserverON", false)) {
        ClassStorage.SetBool("ObserverON", false);
        Notification("Observer mode deactivated.", true);
      } else {
        ClassStorage.SetBool("ObserverON", true);
        Notification("Observer mode activated.", true);
      }
    }
  }
}
```

`if` can have an `else` block, and `else if condition { ... }` chains more
conditions. The second argument to `Notification` makes it an important
notification. It's optional and defaults to `false`.

A storage key holds one type of value. A key that holds a `bool` can't also
hold a `string`.

## Several events, one trigger

```aa2m
trigger "Observer" {
  on CARD_INITIALIZED;
  on CARD_ADDED;
  ...
}
```

The trigger runs on either event. `CARD_INITIALIZED` fires when a saved class
with the card loads and when the card joins the class, so the switch is set
up in both cases.

## Ending a trigger early

When a trigger has nothing to do, it can stop instead of wrapping everything
in an `if`. Tutor starts like this:

```aa2m
StopThreadIf(!ThisCard.GetBool("Tutor", true));
StopThreadIf(ThisCard != TriggeringCard && ThisCard != Context.NpcAnswerTarget);
```

`StopThreadIf(condition)` ends the trigger when the condition is true.
`StopThread()` ends it unconditionally.

## Loops

Pacifist resets its opinions about everyone in the class at the end of each
period. It walks through every seat with `for`:

```aa2m
trigger "Reset" {
  on PERIOD_ENDS;
  let i: card = 0;
  ...
  if (ThisCard.GetBool("Pacifist", true)) {
    for i from 0 to 25 {
      if (Globals.IsSeatFilled(i) && ThisCard != i) {
        ThisCard.SetOpinion(Constants.Opinion.ILL_GET_YOU, i, 0);
        ThisCard.SetOpinion(Constants.Opinion.TOGETHER_FOREVER, i, 0);
      }
    }
  }
}
```

`for i from 0 to 25` counts `i` up from 0, and the loop variable has to be
declared first. `Globals.IsSeatFilled(i)` skips empty seats.
`Constants.Opinion.ILL_GET_YOU` is a named value from the game. The
[built-ins reference](../reference/builtins/index.md) lists them all.

`loop { ... }` repeats until a `break;`, and `break if condition;` leaves when
the condition is true. `continue;` skips to the next round.

Pacifist also keeps a card in a global, `global PacifistOpponent: card = 25;`.
Seat 25 doesn't exist, so the module uses it to mean "nobody".

Next: [Constants](constants.md).
