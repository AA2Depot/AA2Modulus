---
description: Reuse a block of actions in Tutor with a macro, then move the macro into a library file.
---

# Macros and libraries

Tutor helps other characters study. It has two triggers, one for NPC
conversations and one for the player's, and both end with the same three
lines:

```aa2m
trainee.SetIntelligenceValue(trainee.IntelligenceValue + coach.IntelligenceRank);
trainee.AddIntelligenceModifier("oof", 0);
WriteLog(ThisCard.FullName + (" is helping " + (trainee.FullName + " with their studies!")));
```

In the second line, `"oof"` names the modifier. A card keeps its modifiers by
name, and adding one under a name it already has replaces the old value. With
a value of 0 the modifier adds nothing, yet
[`AddIntelligenceModifier`](../reference/builtins/actions/character-modification.md#action-117)
still recalculates the card's intelligence: it keeps the value between 100 and
999, updates the intelligence rank and saves the value with the class.
[`SetIntelligenceValue`](../reference/builtins/actions/character-modification.md#action-40)
only writes the raw number, which is probably why Tutor calls both.

Fix a bug in one copy and you have to remember the other.

## A macro

A macro is a named block of actions. Define it outside the module:

```aa2m
macro "study_help" {
  param coach card;
  param trainee card;
  trainee.SetIntelligenceValue(trainee.IntelligenceValue + coach.IntelligenceRank);
  trainee.AddIntelligenceModifier("oof", 0);
  WriteLog(ThisCard.FullName + (" is helping " + (trainee.FullName + " with their studies!")));
}

module "Tutor" {
  ...
  trigger "Bonus Gains" {
    on NPC_AFTER_RESPONSE;
    let coach: card = 25;
    let trainee: card = 25;
    ...
    if (Context.NpcAnswerConversationId == Constants.Conversation.DO_STUDY && Context.NpcEffectiveResponseSuccess) {
      ...
      study_help(coach, trainee);
    }
  }
  ...
}
```

Each `param` has a name and a type, and a call passes one value per parameter
in the same order. The compiler copies the macro's actions into every place
you call it, so this Tutor also compiles to exactly the same bytes as the
original.

A macro can only use its parameters and the game's built-ins. It can't read
or change the caller's variables, so everything it needs comes in through a
parameter. A macro can't return a value either.

An argument is copied wherever its parameter appears. If you pass
`Math.RandomInt(1, 6)` and the macro uses that parameter twice, it rolls
twice. Store the roll in a variable first if you need the same number.

## A library

A macro in the module file is only available to that module. To use it
elsewhere, move it to a library: a file ending in `.aa2mi` that holds macros,
constants and trigger templates but no module.

```text
tutor/
  tutor.aa2m
  libraries/
    study.aa2mi
```

`libraries/study.aa2mi` holds the macro, unchanged. The module imports it:

```aa2m
import "libraries/study.aa2mi";

module "Tutor" {
  ...
}
```

The path is relative to the file that has the `import`. A library can import
other libraries. Everything that gets imported shares one set of names, so two
macros with the same name are an error, even in different files.

Imports exist only in the source. The compiled module has the macro's actions
in it and doesn't need the library in the game. This version of Tutor, too,
compiles to the original bytes.

Next: [Several modules](several-modules.md).
