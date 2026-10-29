---
description: Macros, reusable blocks of actions with typed parameters.
---

# Macros

```aa2m
macro "study_help" {
  param coach card;
  param trainee card;
  trainee.SetIntelligenceValue(trainee.IntelligenceValue + coach.IntelligenceRank);
  trainee.AddIntelligenceModifier("oof", 0);
}

module "Tutor" {
  trigger "Bonus Gains" {
    ...
    study_help(coach, trainee);
  }
}
```

A macro is a named block of statements. A call copies the statements into
the trigger, so the compiled module looks as if you had typed them there.
Macros are declared outside the module, in a `.aa2m` file or a
[library](libraries.md).

## Parameters

Each `param` has a name and a type: `card`, `int`, `float`, `bool` or
`string`. Parameters come before the statements. A call passes exactly one
value per parameter, in order. A macro without parameters is called as
`name();`.

An argument is copied to every place its parameter is used. Pass
`Math.RandomInt(1, 6)` to a parameter used twice and it rolls twice. An
argument the macro never uses is checked but never runs.

## What a macro can use

- its parameters,
- the game's built-ins,
- constants declared outside any module,
- other macros.

It can't read or assign the caller's variables or declare its own, and it
can't assign to its parameters. Pass anything it needs as a parameter. A
`break` or `continue` inside a macro needs a loop inside the same macro.

A macro gives no value back, so it can only be used as a statement.

## Names

Macro names are ordinary names and aren't case-sensitive: `study_help` and
`Study_Help` are the same macro. A macro can't have the name of an action.

Every macro is checked, even one nobody calls. An unused macro adds nothing
to the compiled module.
