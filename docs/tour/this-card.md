---
description: Why module triggers check ThisCard and TriggeringCard, and how a module marks the card it is installed on.
---

# ThisCard and TriggeringCard

A module is installed on a card, but its triggers react to the whole class.
When any card joins, `CARD_ADDED` fires, and every trigger listening for it
runs. A module on five cards runs its `Init` trigger five times for each card
that joins, once for each card it's installed on.

Two built-ins tell those runs apart:

- `ThisCard` is the card the module is installed on, the one this copy of the
  trigger belongs to.
- `TriggeringCard` is the card the event is about, here the card that just
  joined.

So `if (TriggeringCard == ThisCard)` means "only when the card that joined is
my own card". Without it, Race-Human would add `Human ` to its own card's
`Race` entry every time anyone joined the class.

## Marking the card

Here is the `Init` trigger from Naive. Tutor, Pacifist and many other modules
have the same one with their own name in it:

```aa2m
trigger "Init" {
  on CARD_ADDED;
  if (TriggeringCard == ThisCard) {
    ThisCard.SetBool("Naive", ThisCard.GetBool("Naive", true));
  }
}
```

When the card with the module joins, it stores a `Naive` entry on itself. If
the entry is already there, it keeps the value it had, and otherwise it sets
it to `true`. The other triggers then start with a check like this:

```aa2m
if (ThisCard.GetBool("Naive", true)) {
  ...
}
```

The entry is how the module marks the card that has it installed. It's an
ordinary storage entry, so other modules can read it too, for example to
check whether a card has Naive.

This is the module's own flag. It has nothing to do with the personality
traits you tick in AA2Edit's character editor.

## Other cards in an event

Many events involve more than one card, and the event tells you who the
others are through `Context` values. During a conversation event,
`Context.NpcTalkTarget` is the character the NPC talks to. When Pacifist's
own card is about to start a fight, it cancels the action and clears two of
its opinions about the card it was going to fight:

```aa2m
trigger "NPCWantsToTalk" {
  on NPC_WANT_TALK_WITH;
  if (ThisCard == TriggeringCard) {
    if (Context.NpcActionId == Constants.Conversation.FIGHT) {
      ThisCard.CancelAction();
      ThisCard.SetOpinion(Constants.Opinion.TOGETHER_FOREVER, Context.NpcTalkTarget, 0);
      ThisCard.SetOpinion(Constants.Opinion.ILL_GET_YOU, Context.NpcTalkTarget, 0);
    }
  }
}
```

The real trigger also catches slaps, murders and a few other actions, and it
writes the two opinions as plain `4` and `5`, the values of those constants.
Decompiling keeps a plain number as a number, because the module stores it
differently from a constant.

Each event has its own `Context` values. After a response, Pacifist stores
`Context.NpcAnswerTarget` in a global, `PacifistOpponent`, so its later
triggers can check both sides of the argument:

```aa2m
if (ThisCard == TriggeringCard || PacifistOpponent == TriggeringCard) {
  ...
}
```

Each `Context` value's description in the
[built-ins reference](../reference/builtins/expressions/event-response.md)
says which events give it a value. `Context.NpcTalkTarget`, for example, has
one only in the NPC talk events and `CONVERSATION_END`.

## Seats and the card type

A card is identified by its seat in the class, a number from 0 to 24. The
`card` type holds a seat. It's stored as a plain `int`, but the compiler uses
it to stop you passing a number where a character is expected:

```aa2m
let coach: card = ThisCard;
coach.SetVirtue(3);       // fine
let amount: int = 3;
amount.SetVirtue(3);      // error: expected card, found int
```

If you really have a seat number in an `int`, `Card(amount)` turns it into a
card.

Next: [Reacting to the game](game-events.md).
