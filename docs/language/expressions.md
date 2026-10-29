---
description: Operators, built-in calls, card members, namespaces and named game values.
---

# Expressions

## Operators

From lowest to highest precedence:

| Operators | Meaning | Operands |
| --- | --- | --- |
| `\|\|` | or | `bool` |
| `&&` | and | `bool` |
| `==` | equal | two `int`, two `float` or two `string` |
| `!=` | not equal | two `int` or two `float` |
| `<` `<=` `>` `>=` | comparison | `int` or `float` |
| `+` `-` | add, subtract | `int` or `float`, and `+` joins strings |
| `*` `/` | multiply, divide | `int` or `float` |
| `!` | not | `bool` |

`||` and `&&` skip the right side when the left side already decides the
result. A comparison can't be chained, so write `a < b && b < c`. Use
parentheses whenever you're unsure.

The game has no `==` for `bool` and no `!=` for `string`. Test a `bool`
directly (`if (flag)`, `if (!flag)`) and write `!(a == b)` for two strings.

Both operands of an arithmetic operator have the same type. The compiler
doesn't convert for you:

```aa2m
ThisCard.SetPoints(Context.NpcTalkTarget, ToFloat(love), ToFloat(like), 0.0, 0.0, ToFloat(spare));
```

## Calling built-ins

Actions are statements and end with `;`. Expressions give a value:

```aa2m
Notification("Observer mode activated.", true);
let roll: int = Math.RandomInt(1, 6);
```

A built-in without parameters has no parentheses: `Globals.CurrentDay`,
`ThisCard`. Some parameters have a default and can be left out, like the
second argument of `Notification`.

Built-ins are grouped under a few names:

| Prefix | Holds |
| --- | --- |
| `Globals` | The state of the game and the class: `Globals.CurrentPeriod`, `Globals.PlayerCharacter`. |
| `Context` | Values the current event fills in: `Context.NpcTalkTarget`, `Context.KeyPress`. |
| `Conversation` | The conversation in progress. |
| `H` | The H scene in progress. |
| `Npc` | NPC actions. |
| `ClassStorage` | Entries stored for the whole class. |
| `Math`, `Text` | Numbers and strings. |
| `Constants` | Named game values, such as `Constants.Conversation.DO_STUDY`. |
| (none) | `ThisCard`, `TriggeringCard`, `Notification`, `WriteLog`, `StopThread`, `StopThreadIf`, `ToInt`, `ToFloat`, `ToString` and a few more. |

A `Context` value only has a meaning in the events its description names.
Read in another event, it gives 0 or a value that means nothing, and for
some the compiler reports an [error](hazards.md).

## Card members

Built-ins that act on a character are written after a card:

```aa2m
ThisCard.SetVirtue(3);
let virtue: int = coach.Virtue;
coach.AddLike(Context.NpcTalkTarget, 30);
trainee.SetIntelligenceValue(trainee.IntelligenceValue + coach.IntelligenceRank);
```

The card in front of the dot is the character the built-in reads or changes.
Members without parameters, like `coach.Virtue`, read like a property. To
change one, call its `Set` member: `coach.SetVirtue(5)`.

The card in front can be:

- `ThisCard`, `TriggeringCard` or another card built-in: `Globals.PlayerCharacter.Virtue`
- a variable: `coach.Virtue`
- another member: `coach.Target.Virtue`
- a call: `Conversation.Actor(0).Virtue` or `Card(seat).Virtue`
- anything else in parentheses: `(3).Virtue` for the card in seat 3

Card storage is a set of members too: `GetInt`, `SetInt`, `GetBool`,
`SetString`, `RemoveInt` and so on. Each getter takes a fallback value that it
returns when the entry doesn't exist:

```aa2m
ThisCard.SetBool("Naive", ThisCard.GetBool("Naive", true));
```

## Named game values

`Constants.<Group>.<NAME>` names a fixed value from the game, like a
conversation or a room:

```aa2m
if (Context.NpcAnswerConversationId == Constants.Conversation.FIGHT) {
```

The [built-ins reference](../reference/builtins/index.md) lists them under
Named constants.

## Variables with built-in names

If a variable has the same name as a built-in without parameters, the bare
name means the variable. Write `Name()` to get the built-in.
`ThisCard` and `TriggeringCard` are the exception: they always mean the
built-in.
