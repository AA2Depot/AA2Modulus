---
description: Race-Human, the smallest real module, explained line by line.
---

# A first module

Race-Human is about as small as a useful module gets. It records on a card
that the character is human, so other modules can read it later.

```aa2m
module "Race-Human" {
  description "Is a human";

  trigger "Init" {
    on CARD_ADDED;
    let race: string = "Human ";
    if (TriggeringCard == ThisCard) {
      ThisCard.SetString("Race", race + ThisCard.GetString("Race", ""));
    }
  }
}
```

Compile it and you get the original Race-Human file back, byte for byte:

```bash
aa2modulus compile race-human.aa2m -o Race-Human
```

## The module

`module "Race-Human" { ... }` holds everything else. Its name is what AA2Edit
shows once the module is on a card. Each file holds one module.

`description` is the text AA2Edit shows for the module. A long description can
span several lines with `"""`:

```aa2m
description """
  Observer : Prevents NPCs from interacting with you.

  [PC Only]
  """;
```

The indentation of the closing `"""` is removed from every line.

## The trigger

A trigger is a list of things to do when something happens in the game. A
module can have as many as it needs, and each one has a name.

`on CARD_ADDED;` says when the trigger runs. `CARD_ADDED` fires when a card is
added to the class. A trigger can list several events, and it runs for any of
them. The [built-ins reference](../reference/builtins/events/card.md) lists
every event.

## A variable

```aa2m
let race: string = "Human ";
```

`let` declares a variable that belongs to this trigger. It has a name, a type
(`string`, `int`, `float`, `bool` or `card`) and a starting value. Other
triggers can't see it.

## The check

```aa2m
if (TriggeringCard == ThisCard) {
  ...
}
```

`ThisCard` is the card the module is installed on, and `TriggeringCard` is the
card that caused the event. This check is in nearly every trigger, and the
[next page](this-card.md) explains why.

## Card storage

```aa2m
ThisCard.SetString("Race", race + ThisCard.GetString("Race", ""));
```

Every card has a storage area of named entries that is saved with the class.
`ThisCard.GetString("Race", "")` reads the `Race` entry and gives back `""` if
it doesn't exist yet. `+` joins the two strings, and `SetString` writes the
result back. If another race module already wrote something there, this one
adds `Human ` in front of it.

`ThisCard.SetString(...)` is written like a method call because these
built-ins act on a card. The card in front of the dot is the one they read or
change.

Every statement ends with `;`, and `//` starts a comment that runs to the end
of the line.

Next: [ThisCard and TriggeringCard](this-card.md).
