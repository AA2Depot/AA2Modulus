---
description: if, else, loops, for loops and ending a trigger early.
---

# Control flow

## if and else

```aa2m
if (ClassStorage.GetBool("ObserverON", false)) {
  ClassStorage.SetBool("ObserverON", false);
} else if (Globals.CurrentPeriod == 1) {
  Notification("Observer mode is active.", true);
} else {
  ClassStorage.SetBool("ObserverON", true);
}
```

The condition must be a `bool`. Parentheses around it are optional, and the
braces are required.

## loop

`loop` repeats its block until a `break` runs:

```aa2m
loop {
  count = count + 1;
  break if count >= 10;
}
```

`break;` leaves the loop and `continue;` starts the next round. Both can take a
condition: `break if condition;`, `continue if condition;`. There's no
`while`, so put the condition in a `break if` at the top.

## for

```aa2m
let i: card = 0;
for i from 0 to 25 {
  if (Globals.IsSeatFilled(i) && ThisCard != i) {
    ThisCard.SetOpinion(Constants.Opinion.ILL_GET_YOU, i, 0);
  }
}
```

`for` counts a variable from one value to another. Declare the variable
first, as an `int` or a `card`. Looping over every seat with a `card`
variable, as here, is the usual way to visit every character.

`break` and `continue` work in `for` too.

## Ending a trigger early

`StopThread();` ends the trigger. `StopThreadIf(condition);` ends it when the
condition is true, which keeps the rest of the trigger from being nested
inside an `if`:

```aa2m
StopThreadIf(!ThisCard.GetBool("Tutor", true));
StopThreadIf(ThisCard != TriggeringCard && ThisCard != Context.NpcAnswerTarget);
```

## Standalone branches

AA2Edit stores `else if` and `else` as separate actions, so a module made in
AA2Edit can have one that isn't attached to an `if`. The decompiler writes
those as `ElseIf condition { ... }` and `Else { ... }`, with capitals. You
won't need them in modules you write yourself.
