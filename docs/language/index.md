---
description: "The basics of .aa2m source files: file kinds, comments, names, literals, types and variables."
---

# Language basics

This section describes the whole language, one topic per page. If you're new
to it, the [tour](../tour/index.md) is a gentler start. The exact syntax is in
the [grammar](../grammar.md).

## Files

| Extension | Holds |
| --- | --- |
| `.aa2m` | Exactly one `module`, plus any imports, macros and constants around it. |
| `.aa2mi` | A library: imports, macros, constants and trigger templates, but no module. |

Source files are UTF-8. Spaces, tabs and line breaks don't matter, except
inside strings.

## Comments

`//` starts a comment that runs to the end of the line. `/* ... */` can span
lines, but it doesn't nest. Comments aren't stored in the compiled module, so
decompiled source never has them.

A comment directly above a declaration shows up in the editor when you hover
that name.

## Names

A name starts with a letter or `_` and continues with letters, digits and
`_`. Built-ins use dotted names such as `Globals.CurrentDay`, and the first
part (`Globals`, `Context`, `Constants`, ...) is case-sensitive. The rest of a
built-in name isn't, but the editor and the decompiler always write the
spelling shown in the [built-ins reference](../reference/builtins/index.md).

Variable and constant names are case-sensitive. Macro names aren't.

Words like `if`, `trigger` or `card` are reserved. To give a variable a name
that is a reserved word or that has spaces in it, quote it where you declare
it and use `variable("...")` where you read or assign it:

```aa2m
let "my count": int = 0;
variable("my count") = variable("my count") + 1;
```

`ThisCard` and `TriggeringCard` always mean the built-ins. You can't declare
a variable or constant with either name.

## Literals

| Type | Examples |
| --- | --- |
| `int` | `0`, `42`, `-1` (32-bit, from -2147483648 to 2147483647) |
| `float` | `1.0`, `0.5`, `.25`, `1.5e3` (32-bit, always with a decimal point) |
| `bool` | `true`, `false` |
| `string` | `"text"`, with JSON escapes such as `\"`, `\n` and `\u00e9` |

Strings use double quotes. A `description` can also use a block string that
spans lines, described in [modules and triggers](modules.md#description).

## Types

| Type | Holds |
| --- | --- |
| `int` | Whole numbers. |
| `float` | Decimal numbers. |
| `bool` | `true` or `false`. |
| `string` | Text. |
| `card` | A character's seat in the class. |

`card` is stored in the game as an `int`. The compiler uses it to catch a
number passed where a character is expected, or the other way round. A card
can be used wherever an `int` is expected. An `int` that isn't a plain number
needs `Card(...)` to be used as a card:

```aa2m
let partner: card = Card(ThisCard.GetInt("partner", 25));
```

A card can be any seat number. The type doesn't check that the seat exists or
has a character in it. `Globals.IsSeatFilled(seat)` does.

There are no automatic conversions between other types. Use `ToInt`,
`ToFloat` and `ToString`.

## Variables

A trigger declares local variables with `let`, and a module declares globals
with `global`. Both need a type and a starting value:

```aa2m
global PacifistOpponent: card = 25;
let love: int = 0;
```

Assign with `=`. There's no `+=` or `++`, so write `love = love + 1;`.

A local is visible in its whole trigger, including in lines above its
declaration, but not in other triggers. A global is visible in every trigger
of the module and is saved on the card. If a local and a global share a name,
the global wins.

A module can only use variables it declares. See
[modules and triggers](modules.md#globals) for more on globals.
