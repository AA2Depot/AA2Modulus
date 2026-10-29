---
description: Compile-time constants with const, their scope and how to refer to them.
---

# Constants

```aa2m
const Flag: string = "Naive";
const Threshold: int = 29;
```

A constant names a value. The compiler puts the value in everywhere the name
is used, so a module with constants compiles to the same bytes as one with
the values typed out. Constants never reach the game, and decompiled source
shows the plain values.

The type is required: `int`, `float`, `bool` or `string`. The value is a
plain value of that type or another constant of the same type. There's no
arithmetic in a constant.

## Where they're visible

| Declared | Visible in |
| --- | --- |
| At the top of a `.aa2m` file, outside the module | The module, the file's macros and the templates it uses. |
| In a library | Every file that imports the library, directly or through another library. |
| Inside the module | That module only, not in macros or templates. |

Order doesn't matter: a constant can be used above its declaration.

All the constants a module can see share one set of names, so two with the
same name are an error even if they're in different files. A constant also
can't share a name with a global or local it's visible to.

## Referring to them

Use the bare name when it's an ordinary name. When the name has spaces or is
a reserved word, quote it in the declaration and use `const("...")`:

```aa2m
const "With Spaces": string = "Naive card";
Notification(const("With Spaces"));
```

`const("...")` works for every constant and only ever means a constant, the
same way `variable("...")` only ever means a variable.

A global's starting value can be a constant:

```aa2m
const DefaultKey: int = 81;

module "Observer" {
  global OBS_KEY: int = DefaultKey;
  ...
}
```

Assigning to a constant is an error.
