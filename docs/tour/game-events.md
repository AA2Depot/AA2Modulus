---
description: Naive reacts to conversations and relationship changes with nested conditions, variables and arithmetic.
---

# Reacting to the game

Naive is a character who "believes that everyone is a nice person at heart".
After a conversation, if their dislike or hate for the other person has grown
too high, Naive turns it back into love and like. Here's the whole module:

```aa2m
module "Naive" {
  description "Believes that everyone is a nice person at heart. [PC/NPC Module]";

  trigger "Init" {
    on CARD_ADDED;
    if (TriggeringCard == ThisCard) {
      ThisCard.SetBool("Naive", ThisCard.GetBool("Naive", true));
    }
  }

  trigger "a" {
    on CONVERSATION_END;
    let spare: int = 0;
    let love: int = 0;
    let like: int = 0;
    if (ThisCard.GetBool("Naive", true)) {
      if (ThisCard == TriggeringCard) {
        if (ThisCard.Dislike(Context.NpcTalkTarget) > 29 || ThisCard.Hate(Context.NpcTalkTarget) > 29) {
          love = TriggeringCard.Love(Context.NpcTalkTarget);
          like = TriggeringCard.Like(Context.NpcTalkTarget);
          spare = 900 - (like + love);
          ThisCard.SetPoints(Context.NpcTalkTarget, ToFloat(love), ToFloat(like), 0.0, 0.0, ToFloat(spare));
          WriteLog(ThisCard.FullName + (" doesn't believe " + (Context.NpcTalkTarget.FullName + " is truly bad.")));
        }
      }
    }
  }

  trigger "Gain" {
    on RELATIONSHIP_POINT_CHANGED;
    if (ThisCard.GetBool("Naive", true)) {
      if (ThisCard == TriggeringCard) {
        Context.SetAppliedPoints(Context.AppliedLove, Context.AppliedLike, 0, 0);
      }
    }
  }
}
```

You already know `Init` from the [previous page](this-card.md). The other two
triggers are new.

## After a conversation

`CONVERSATION_END` fires when two characters finish talking. `TriggeringCard`
is one of them and `Context.NpcTalkTarget` is the other.

The trigger declares three `int` variables at the top. Locals can be declared
anywhere in a trigger, but putting them first is easier to read.

```aa2m
if (ThisCard.Dislike(Context.NpcTalkTarget) > 29 || ThisCard.Hate(Context.NpcTalkTarget) > 29) {
```

`ThisCard.Dislike(...)` reads how much this card dislikes the other one. Some
built-ins take arguments in parentheses. Others, like `ThisCard.FullName`,
don't, and you read them like a property. `||` means "or", `&&` means "and" and
`!` means "not". Comparisons use `==`, `!=`, `<`, `<=`, `>` and `>=`.

```aa2m
love = TriggeringCard.Love(Context.NpcTalkTarget);
like = TriggeringCard.Like(Context.NpcTalkTarget);
spare = 900 - (like + love);
```

`=` assigns a new value to a variable that already exists. Arithmetic uses
`+`, `-`, `*` and `/`, and parentheses group as you'd expect.

```aa2m
ThisCard.SetPoints(Context.NpcTalkTarget, ToFloat(love), ToFloat(like), 0.0, 0.0, ToFloat(spare));
```

`SetPoints` takes `float` values. The compiler never converts between `int`
and `float` for you, so `ToFloat(...)` does it explicitly. Write a float with a
decimal point, like `0.0`. If you forget a conversion, the error tells you
which type it expected.

`WriteLog` writes a line to AAUnlimited's log file, which is useful while you
test a module. `Notification("...")` shows the text on screen instead.

## Changing what the game does

```aa2m
trigger "Gain" {
  on RELATIONSHIP_POINT_CHANGED;
  ...
  Context.SetAppliedPoints(Context.AppliedLove, Context.AppliedLike, 0, 0);
```

Some events let a trigger change their outcome. `RELATIONSHIP_POINT_CHANGED`
fires as relationship points are being updated. `Context.AppliedLove` and
`Context.AppliedLike` hold the change the game is about to make, and
`Context.SetAppliedPoints` replaces it. Naive keeps the love and like and
drops the dislike and hate.

## Try it

Change the threshold from `29` to `59`, compile, and decompile the result. The
decompiled source is the same text with your change in it. To see the binary
the way AA2Edit shows it, run `aa2modulus inspect` on the compiled file.

Next: [Keeping state](state.md).
