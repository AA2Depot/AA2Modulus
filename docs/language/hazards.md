---
description: Known AAUnlimited bugs the compiler reports, and how @allow acknowledges them.
---

# Known AAUnlimited bugs

A few built-ins don't work in AAUnlimited the way their description says. The
compiler reports every use as an error. These are bugs in AAUnlimited, and the
fixes belong there.

| Code | What goes wrong |
| --- | --- |
| `REVIEWED_VALUE_TYPE_MISMATCH` | `Context.NpcOriginalResponse` and `Context.NpcCurrentResponse` have a value only in `NPC_RESPONSE`, and `Conversation.IsAnswering` only in `PC_RESPONSE` and `PC_AFTER_RESPONSE`. In any other event they read leftover memory, which can change from one read to the next. |
| `EXPRESSION_METADATA_RETURN_TYPE_MISMATCH` | AAUnlimited declares `Context.NpcOriginalResponse` as a `bool` but it gives an `int`, and saving the module in AA2Edit breaks it. |
| `NATIVE_DEFECTIVE_EXPRESSION` | `Text.Replace` can't work: AAUnlimited reads its first argument as a string but only accepts an `int` there. |

When the event is unknown, for example in a trigger with no events, the first
case is a `REVIEWED_VALUE_CONTEXT_UNKNOWN` warning instead.

## Acknowledging a bug with @allow

Some real modules depend on one of these bugs. To compile one anyway, put
`@allow(CODE)` in front of the statement, event, local, trigger or module
that has the problem:

```aa2m
trigger "NPC Flag" {
  on NPC_AFTER_RESPONSE;
  @allow(REVIEWED_VALUE_TYPE_MISMATCH)
  if (Context.NpcCurrentResponse == 0) {
    Notification("answered 0", true);
  }
}
```

The error becomes a warning, and a second warning says that bypassing it is
not recommended. The compiled module is the same with or without the line.

Only the three codes above can be acknowledged. An `@allow` that ends up
covering nothing is an error, so you'll notice when an AAUnlimited fix makes
it unnecessary. The decompiler adds `@allow` lines itself when a module needs
them.
