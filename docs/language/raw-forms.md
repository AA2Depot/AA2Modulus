---
description: Raw records the decompiler writes for parts of a module that have no readable form.
---

# Raw forms

Sometimes the decompiler meets something it can't write as readable source:
an ID the toolchain doesn't know, or a record whose types don't match what
the game expects. It writes that part with its numbers instead:

```aa2m
raw_action 9002(raw_expression type 77 9004 { parameters [ ]; });
raw_expression int 3 {
  named_constant int 7;
}
```

| Form | Stands for |
| --- | --- |
| `raw_action ID(...)` | An action by its ID. |
| `raw_event ID;` | An event by its ID. |
| `raw_expression TYPE ID { ... }` | An expression by its result type and ID. |

Every raw record comes with a `RAW_FALLBACK` warning that gives the reason.
Raw records are checked as strictly as readable ones. One with a known ID
compiles back to the same bytes, and you can leave it alone. One with an ID
the toolchain doesn't know fails to compile, because there's nothing to check
it against. You won't need to write raw records yourself.

## Exact float values

A `float` in the game is 32 bits. When a decompiled value can't be written
exactly as a decimal, the decompiler writes its bits:
`float_bits(0x7FC00000)`. That's an ordinary float value you can use
anywhere.
