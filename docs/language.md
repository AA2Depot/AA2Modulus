# `.aa2m` Language Reference

Status: unified source language, version 16

`.aa2m` is one readable source language. It supports ordinary programming
syntax while compiling through a separate Bound HIR into the AA2 Serialized IR.
The normative grammar is in [grammar](grammar.md).

Blocks containing a complete module can be compiled as files. Other blocks
are expression, statement, or declaration fragments for the enclosing module,
trigger, or library described in the text. See the [quick start](../README.md#quick-start)
for a maintained input and executable CLI workflow.

## Basic Module

```text
module "Notification Example" {
  description "Show a notification when a card is added to class";

  trigger "On Card Added" {
    on CARD_ADDED;
    Notification("A card was added to class");
  }
}
```

The second `Notification` argument defaults to `false` and is inserted during
binding, so Bound HIR and SIR both contain the explicit argument. Write it
explicitly when it is `true`.

A description that spans lines is a `"""` block; the closing `"""` sets the
indentation that is removed (see [lexical forms](grammar.md#lexical-forms)):

```text
  description """
    First line.

    Second paragraph.
    """;
```

## Dependency Metadata

Each `depends_on "Provider";` declaration appends one native dependency string.
Strings retain their exact text and declaration order, including during decode,
decompile, and structural parse/encode recovery. Omitting declarations writes an
empty vector; no empty block is needed.

The pinned AAUnlimited exporter derives these names from globals owned by attached
modules, but its module loader does not resolve or enforce the names. `depends_on`
does not load another module, supply globals, establish card membership/load order,
or import `.aa2mi` definitions. Declare every global the module reads (see
[undeclared variables](#undeclared-variables)) and use `import` for source
definitions.

Native export has further limits ([evidence](native-format.md#dependency-evidence)):
it scans only action parameters, so a global used only in event parameters or
local default expressions is missed and the module can export with empty globals
and dependencies yet fail on a clean card. Ownership is by global name alone, the
first attached module declaring it; there is no dependency graph or cycle
handling because nothing consumes the strings. Unpacking a module copies its
triggers and removes the module but keeps its globals, so exported dependencies
are almost always empty (all 727 audited working modules had none), which
supports the empty default.

Strict source/model validation rejects empty or whitespace-only names, self names,
and duplicate names with `INVALID_MODULE_DEPENDENCY` or
`DUPLICATE_MODULE_DEPENDENCY`. The model APIs' explicit `profile="native"` reports all these metadata-policy
findings as warnings. Variable resolution, types, and other native checks still
apply under that profile. Source validation/compilation remains strict.

Decompilation retains invalid dependency records and reports strict diagnostics
alongside recovered source. The recovered source keeps those records; fix the
reported errors before compiling it.

## Operators and Calls

```text
module "Expressions" {
  trigger "Conversation" {
    on CONVERSATION_END;

    if ((ThisCard.Dislike(Context.NpcTalkTarget) > 29) ||
        (ThisCard.Hate(Context.NpcTalkTarget) > 29)) {
      Notification(ThisCard.FullName + " has been added to class");
    }
  }
}
```

Supported operators are `||`, `&&`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `+`,
`-`, `*`, `/`, and prefix `!`. Operator overloads are selected using operand
types and the shipped metadata snapshot. Numeric conversions must be explicit,
for example `ToFloat(love)`.

Precedence increases through `||`, `&&`, equality (`==`, `!=`), relational
comparison (`<`, `<=`, `>`, `>=`), addition/subtraction, multiplication/division,
and prefix `!`. Equality and relational tiers each permit one comparison;
parenthesize nested comparisons. Version 4 separates those two tiers to match
the shipped policy. Policy may select compatible overloads and defaults within the [fixed syntax contract](metadata.md#fixed-operator-syntax).

Float values use IEEE-754 binary32 wire semantics. Use `float_bits(0x...)` when
exact recovery matters for signed zero, subnormals, infinities, or NaN payloads.
The formatter emits this form automatically for unusual decoded float values.
Ordinary decimal literals that overflow the finite binary32 range produce
`FLOAT_OUT_OF_RANGE` during binding. Int literals outside the int32 range
(`-2147483648` to `2147483647`) produce `INT_OUT_OF_RANGE` during binding; the
sign is part of the literal, so `-2147483648` is valid.

Zero-parameter expressions use bare names such as `ThisCard` and
`TriggeringCard`. Calls with parameters use ordinary function-call syntax.
Use `Name()` to select a zero-argument expression over a variable or constant
of the same name; `ThisCard` and `TriggeringCard` are [protected](#protected-names)
and never need it.

### Protected names

`ThisCard` and `TriggeringCard` are protected: the language policy lists them in
`protected_names`, and matching is case-insensitive. A bare `ThisCard`,
`ThisCard.Virtue` or `TriggeringCard.AddLike(x, 5)` always means the built-in;
variables and constants never shadow it. Declaring a bare identifier with a
protected name (global, `let`, parameter, `const`, macro formal, template slot,
loop variable) is the error `PROTECTED_NAME`.

A native variable that was serialized with such a name stays recoverable. Quote
the declaration and reference it with `variable("...")`, as for keyword names:

```text
let "ThisCard": int = 0;
variable("ThisCard") = 3;
```

The formatter and decompiler emit this form. Constants, macro formals and
template slots are not serialized, so they reject protected names even when
quoted. `ThisCard()` remains a valid zero-argument call.

Version 6 adds qualified built-ins and preferred policy names:

```text
module "Storage" {
  trigger "Init" {
    on CARD_ADDED;
    ClassStorage.SetInt("day", Globals.CurrentDay);
    ThisCard.SetBool("enabled", ThisCard.GetBool("enabled", true));
    if ThisCard.HasLover(TriggeringCard) {
      Notification("Known lover");
    }
  }
}
```

`Globals.*` exposes selected game state; `Context.*` exposes selected event
values. These are runtime expressions, with native context requirements, rather
than serialized constants. Qualified names bypass variable lookup. Dots must
touch their identifier segments, and keyword segments are invalid. A two-segment
name that is not registered may be a [receiver call](#receiver-calls) on a
variable. Storage getters require an explicit fallback;
card storage keeps its leading integer card argument. Use `GetInt`, `GetFloat`,
`GetString`, and `GetBool`, and the corresponding `Set*` names. Card storage
also provides `RemoveInt`, `RemoveFloat`, `RemoveString`, and `RemoveBool`.

Canonical names must be unambiguous for their exact role/signature. An
overloaded name is resolved by exact argument and expected-result types;
otherwise binding reports ambiguity. Operator operands receive
those exact constraints through a bounded candidate search, without casts.

Every action, expression and named constant has a preferred name from the
[naming convention](metadata.md#naming-convention) or, for a card-first built-in,
a [receiver member](#receiver-calls): `Npc.*`, `Context.*`, `Conversation.*`,
`H.*`, `Globals.*`, `ClassStorage.*`, `Lua.*`, `Math.*` and `Text.*` roots, the unqualified core
(`ThisCard`, `Notification`, `WriteLog`, `StopThread`, `StopThreadIf`, `JumpIf`,
`ToInt`, `ToFloat`, `ToString`) and `Constants.<Category>.<UPPER_SNAKE>`. The
formatter and decompiler write these names. A target with a preferred
name accepts only that spelling: native spellings such
as `AddLikePoints`, `NpcTalkTarget`, `ConditionalEndExecution`, `CardAddedToClass`
or the label `LOVE` are unknown names, and the error names the canonical
replacement. Targets without a preferred name (grammar-owned branch and loop
actions, payload markers, `int:99`) keep their native spellings. `Conversation.Id` selects INT/62;
`Constants.EventType.KEY_PRESS` selects native named INT/301, distinct from the
`Context.KeyPress` getter. GUI templates with `%p` placeholders remain display provenance.
Binding, formatting and editor queries share the immutable catalog's forms.

Verified qualified source values lower to primitive literals in expression slots:
`Constants.Room.SCHOOL_GATES` is INT/0 and `Constants.Period.EXAM` is INT/11.
They are distinct from native named references. Unsafe old `SchoolGates`/`EXAM`
aliases produce a targeted shadow-value diagnostic. Equivalent `OPINION_70` rows
select one native INT/282 reference. Existing named wire IDs 298/352/365 preserve
their actual native lookup and save behavior; recovery never replaces them with
these literal aliases. Ordinary decoded literals stay numeric. Globals still
require literal initializers under their existing grammar.

The INT/100 getter, marked readable in the policy, formats as `Context.NpcOriginalResponse` while keeping
its INT wire identity. Its native table declares BOOL, and native re-save produces
unresolved BOOL/100. Strict compilation rejects the declared-type incompatibility;
readable text does not repair that native defect. Event-dependent value types
(policy `[event_values]`) are checked against every known event in the enclosing trigger, including expanded
macro/template uses. See [metadata contracts](metadata.md#preferred-names-and-lookup).

## Receiver Calls

Built-ins whose native slot 0 is a card seat are written as members of that
[card](#cards). The language policy lists them in `[members]`; a card-first target
has no flat qualified name, and its former spellings (`Character.SetVirtue(coach,
3)`, native `SetVirtue(...)`) are rejected with a hint. Members with arguments
and all actions are calls; an expression member with no explicit arguments is a
property and takes no parentheses:

```text
let coach: card = ThisCard;
coach.AddLike(Context.NpcTalkTarget, 30);   // native Add Like Points(coach, target, 30)
let virtue: int = coach.Virtue;             // property getter
coach.SetVirtue(virtue + 1);
let love: int = coach.Love(Context.NpcTalkTarget);
```

Bare built-in receivers: a registered zero-argument `int` expression is a
receiver without parentheses: `ThisCard.Virtue`,
`TriggeringCard.AddLike(coach, 5)`, `Globals.PlayerCharacter.SetVirtue(3)`.
Other receivers are variables (`coach.Virtue`), `variable("any name").Virtue`,
`(expression).Virtue`, call results, or another member (`coach.Target.Virtue`).

The receiver is bound once as native parameter 0 and the explicit arguments fill
the remaining parameters in order, so evaluation order, argument counts and the
serialized records equal the native call. Nothing is reordered, copied, defaulted or
stored in a temporary variable. A receiver is a [`card`](#cards), so an `int`
variable needs `Card(...)`; the type proves neither a live seat nor event
context. Context requirements still come from the functions invoked, not from
receiver syntax.

Resolution of a dotted token such as `a.b.Member` (one lexed token) is ordered:

1. A registered qualified built-in (`Context.NpcTalkTarget`, `ClassStorage.GetInt`).
2. A receiver plus exactly one final member segment. The receiver is the longest
   path before it that is a declared variable (case-sensitive), a registered
   zero-argument `int` expression (`ThisCard`, `TriggeringCard`), or a
   property chain on one of those. A variable wins over a same-named zero-argument
   built-in, as for bare names, except for the [protected names](#protected-names)
   `ThisCard` and `TriggeringCard`, which are always the built-in.
3. Otherwise the name is unknown.

Any name whose first segment exactly equals a registered namespace root
(`Context`, `Globals`, `ClassStorage`, ...) is a static path, so declaring a
variable named `Context` never retargets `Context.NpcTalkTarget`; use
`variable("Context").Virtue` or `(Context).Virtue` to select the variable.
Namespace roots and variable names are case-sensitive; segments after the root,
members and unqualified built-ins are not, so `Context.npctalktarget` resolves
while `context.npctalktarget` is an unknown name whose help names the whole
canonical spelling, `Context.NpcTalkTarget`. When the tail is unknown or matches
several spellings, the help corrects only the root and keeps the tail as typed. Quoted names containing dots are never split. Macro and template
bodies resolve receivers in their own scope and cannot capture caller variables;
a formal used as a receiver repeats its actual wherever the formal is used.

Diagnostics: `UNKNOWN_MEMBER`; `MEMBER_ARITY` (wrong argument count, or a member
with arguments written as a property: `coach.Love` hints `coach.Love(...)`);
`MEMBER_KIND` (an action used as a value, a value used as a statement, a property
written with parentheses: `coach.Virtue()` hints `coach.Virtue`, or an action
written without them: `coach.CancelAction;` is a `MEMBER_KIND` error that hints
`coach.CancelAction(...)`); `MEMBER_ACTION_BLOCK`; `AMBIGUOUS_MEMBER`; and the
usual `SOURCE_TYPE_MISMATCH` for receiver or argument types. Unknown flat
spellings of card-first targets give the usual unknown-name error plus a hint that
rewrites the call (`Character.SetVirtue(coach, 3)` hints `coach.SetVirtue(3)`,
`Character.Virtue(1 + x)` hints `(1 + x).Virtue`), or `<card>.SetVirtue(...)` when
the arguments do not fit. Formatting and decompilation write the member form: the
receiver is a variable name (`variable("x")` for a non-identifier name or a
namespace root), a bare zero-argument built-in, a built-in call
(`Conversation.Actor(0).Virtue`), a chained member, or `(expr)` for literals,
constants and operators; a receiver that cannot be written safely keeps the raw
form. Add a member only in the policy's `[members]` table
([contract](metadata.md#receiver-member-forms)); no method is inferred from a
parameter type, a variable name or a GUI label.

## Cards

Version 16 adds the source-only type `card` for seat values. It is written to
the binary as `int`, so a module declaring `card` produces the same bytes as one
declaring `int`; the type only lets the compiler catch a seat and a number
passed in each other's place:

```text
let coach: card = ThisCard;
let amount: int = 30;
coach.AddLike(amount, coach);    // error: expected card, found int (fix: Card(amount))
coach.AddLike(coach, amount);    // ok
let partner: card = Card(coach.GetInt("partner", 0));   // a stored seat
```

- Card values: `ThisCard`, `TriggeringCard`, every built-in whose result has
  the policy role `card` (`Globals.FindSeat`, `coach.Target`,
  `Context.NpcTalkTarget`, ...; hover shows `-> card`), variables, macro
  formals and template slots declared `card`, and `Card(expression)`.
- Card positions: member receivers, member arguments with role `card`
  (`towards` in `coach.AddLike(towards, amount)`), flat built-in slots with a
  [`[parameter_roles]`](metadata.md#parameter-roles) entry (`H.Start`,
  `Globals.SetPcTarget`, `Globals.RemoveCard`, `Globals.AddCard`,
  `Globals.IsSeatFilled`), assignments to and defaults of `card` variables, and
  the start of a `for` loop whose target is a `card` variable.
- A card position accepts a card value, an integer literal (`3`, `-1`, `(3)`)
  or a constant. Any other `int` is `SOURCE_TYPE_MISMATCH` (`expected card,
  found int`) with a fix that writes `Card(...)` around it. `Card(e)` takes an
  `int` and adds no record. Raw arguments use wire types without card roles;
  a raw `int` expression needs `Card(...)` in a card position.
- A card widens to `int` everywhere else: arithmetic (`coach + 1`), `int`
  arguments (`ToString(coach)`, `coach.SetInt("seat", coach)`), `<` and `>`.
- `==` and `!=` between a card and an `int` other than a literal are the same
  error on the `int` side: compare cards with cards (`coach == Card(seat)`) or
  with a literal (`coach == -1`).
- `card` declares `let`, `global`, macro `param` and template `slot`, never a
  `const` or a raw form. `card` and `Card` are reserved words.

A variable keeps its declared source type through assignments. For a seat
variable initially holding a placeholder, write `let trainee: card = 25;`;
later assignments from `TriggeringCard` or another card value are valid.
Declaring it `int` keeps it `int` even after those assignments. Binding does
not infer type changes from conditionals, and a type mismatch makes no claim
about whether the current value identifies a character.

A card is not checked to be a live seat (0..24) or a filled one, and seats
returned outside their events (`Context.NpcTalkTarget` reads 0, a valid seat)
are still cards; context checks report those reads. Decompilation declares an
`int` variable `card` when its uses as a card are at least as frequent as the
values written to it that are not cards, writes `Card(...)` around those values,
and wraps every other `int` in a card position without changing native fields.
Seats read back from card storage (`GetInt`) stay `Card(...)` reads.

## Variables and Assignment

```text
module "Variables" {
  global enabled: bool = true;

  trigger "Init" {
    on CARD_ADDED;
    let love: int = 0;
    love = TriggeringCard.Love(Context.NpcTalkTarget);
    if (enabled) {
      Notification("Positive");
    }
  }
}
```

Assignments compile to the AAUnlimited `Set Variable` action. A serialized
variable name that is not a valid identifier can be written as
`variable("name with spaces")`.
Quote declarations whose names are keywords, such as `let "true": bool = false;`,
and reference or assign them with `variable("true")`. A bare reserved name in a
declaration, assignment or `for` target, or a constant initializer, is a
`SYNTAX_ERROR` whose fix writes the quoted form. Keyword prefixes do not
reserve longer identifiers: `true_flag` and `breakpoint` are ordinary names.

Lookup searches module globals before locals in the current trigger. Every
local declaration is visible to that trigger's events, defaults, and statements,
including references to later declarations. Locals in other triggers are not
visible. Duplicate globals and duplicate locals within a trigger are rejected;
a local may share a global name, but the global wins. Complete local visibility
is the version 3 scope rule. It uses native global-before-local search priority
within the module environment, without promising runtime initialization order
or safe self/cyclic defaults.

A variable the module never declares is undefined; see
[undeclared variables](#undeclared-variables).

## Compile-Time Constants

Version 13 adds named, typed literal values that the binder substitutes in place:

```text
const Tag: string = "Naive";                    // top level: module, macros, templates
macro "announce" { param "text" string; Notification(Tag + text); }

module "Constants" {
  const "With Spaces": string = "Naive card";   // module item: this module only
  const Alias: string = const("With Spaces");   // constant-to-constant, any order
  const Limit: int = 3;
  global day: int = Limit;                      // global literal initializer
  trigger "Init" {
    on CARD_ADDED;
    ThisCard.SetBool(Tag, true);
    announce(const("With Spaces"));
  }
}
```

See [constants.aa2m](../examples/constants.aa2m) for a compilable module. The type
(`int`, `bool`, `float`, `string`) is required and the value is a literal of
that type (including `float_bits(...)`) or another constant of the same type.
There are no operators. A reference binds to the constant's literal at the
reference's source span, so the output is byte-identical to writing the literal
by hand; constants are never serialized, unused ones emit nothing, and
decompilation shows literals.

Two reference forms, parallel to variables:

| Form | Use | Resolves |
| --- | --- | --- |
| `Limit` (bare name) | only when the name is an ordinary non-keyword identifier (`const Limit` or `const "ModuleName"`) | like a variable name: before unqualified built-ins; never across a dotted namespace root |
| `const("Name")` | every constant; required for names that are not identifiers (spaces, punctuation) or are keywords (`const("true")`); also the explicit form that picks the constant when a variable shares the bare name | constants only (`UNDEFINED_CONST` otherwise), as `variable("Name")` resolves only variables |

`const("X")` is to constants what `variable("X")` is to variables; neither
form sees the other kind, and raw `variable "X"` payloads name variables only.
A constant may be a receiver like a variable (`const LEAD: int = 0;` then
`LEAD.Virtue` or `const("LEAD").SetVirtue(3)`). Names are case-sensitive.
`const` is a reserved keyword; `const_x` and `constant_x` remain identifiers
and `"const"` may be a quoted name.

Scope: top-level constants (outside the module, in module or library units)
join the one transitive import namespace and are visible in the module, macro
bodies and trigger templates. Module-item constants are visible only in their
module (events, global initializers, local defaults, statements and
`import.trigger` slot actuals), not in macros or templates, which stay
hygienic. Both kinds share one namespace per operation: a duplicate name fails
even when unused, and a definition reached through a diamond import is one
definition. Declaration order does not matter.

Collisions are errors, not shadowing: a constant may not share its exact name
with a module global, trigger local, macro formal, template slot or template
local in its visibility. After such a collision, a bare use of the name is
`AMBIGUOUS_CONST`; write `const("X")` or `variable("X")`.

Diagnostics: `DUPLICATE_CONST`, `CONST_NAME_COLLISION`, `AMBIGUOUS_CONST`,
`UNDEFINED_CONST`, `CONST_ASSIGNMENT` (assignment or `for` target naming a
constant), `CONST_CYCLE`, `CONST_NAME`, `CONST_TYPE`, `CONST_UNIT_REQUIRED`
(module-only `parse_source_ast` given top-level constants), plus
`SOURCE_TYPE_MISMATCH`, `INT_OUT_OF_RANGE` and `FLOAT_OUT_OF_RANGE` for the value.

## Validation Profiles

`validate_module` and `compile_module` default to `profile="strict"`: declarations,
references, assignments, and every original GUI expression are checked, including
raw-marked model nodes. Source validation/compilation uses these authoring checks
for readable and raw forms alike. Raw provenance selects source representation;
it does not relax identity, signature, type or scope checks. Binary recovery
(decode, then encode) keeps the bytes without claiming semantic validity.

Event-data callbacks are listed in the policy's `[event_values]`. INT/100
and INT/101 (`Context.NpcOriginalResponse`, `Context.NpcCurrentResponse`) read
their answer only during `NPC_RESPONSE` (event8); in every other event the native
callback executes `return false`. INT/70 (`Conversation.IsAnswering`) reads a
bool field in `PC_RESPONSE`/`PC_AFTER_RESPONSE` (events14/19). AAUnlimited's
evaluator passes the result on without a type check, and a bool `Value` writes
only one byte of its value union, so an int read sees that byte plus leftover
memory. The result is unspecified and can change between reads in one run (an
in-game test read `1060439040`, then `0`). Strict validation reports
`REVIEWED_VALUE_TYPE_MISMATCH` errors for those INT uses (warnings under
`profile="native"`); the message names the events where the value exists and
what the native callback returns in the trigger's event. A trigger with missing
or unknown events reports `REVIEWED_VALUE_CONTEXT_UNKNOWN` warnings that name the
events where the value exists; known events are still checked individually. Context requirements follow expanded expressions
through macros, imports and template slots without changing their identities.
Free macro definitions defer event checks to invocations.

INT/100's declared BOOL mismatch is `EXPRESSION_METADATA_RETURN_TYPE_MISMATCH`
under strict validation, even for unused definitions. Its separate
`NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE` warning records native INT/100 -> BOOL/100
and the absent reload row. Source parse/encode still preserves the original bytes.

`Text.Replace` (STRING/13) cannot work in AAUnlimited: its first parameter is
declared `int`, but the native function reads it as a string. Every use is a
`NATIVE_DEFECTIVE_EXPRESSION` error (a warning under `profile="native"`); the
upstream bug is recorded in [native format](native-format.md) N12 and in the
policy's `[defects]` table ([metadata](metadata.md#native-defects)).

These three findings describe known AAUnlimited hazards, not authoring mistakes;
source can acknowledge them with
[`@allow`](#acknowledging-native-hazards) when a module depends on the native
behavior.

`profile="native"` checks the pinned initialization projection. Conditional
IF/ELSEIF/ELSE children start fresh loop state; Break/Continue without active
loop state is discarded before variable resolution. An inner loop establishes
its own state; ordinary action children retain the enclosing loop state.
Both profiles report located `NATIVE_DISCARDED_CONTROL` warnings. Readable source
can preserve those controls and warns without changing its GUI records.

Native validation resolves variables in events, local defaults, and projected
actions before checking registry signatures and types. Set Variable compares
the target and value expression return types, using registry-declared return
types. Reference/declaration type differences become `VARIABLE_TYPE_MISMATCH`
warnings; assignment/declaration differences use `ASSIGNMENT_DECLARATION_TYPE`.
Unknown executed registry references, expression/signature errors, and unresolved
variables remain errors. Malformed flow that cannot be projected safely reports
`NATIVE_PROJECTION_ERROR`. Structural writer constraints always apply. Native
validation never relaxes raw provenance. Compilation writes the original GUI
tree, including discarded records, without coercing or repairing values.
Event-value context and native re-save hazards are warnings in this profile;
native declared-type consumer checks remain errors as required by initialization.

Passing native checks does not prove safe evaluation: native variable evaluation
returns the stored Value, whose type may differ from its expression's type.
Global value/declaration mismatches and duplicate declarations are warnings in
this profile. [Dependency metadata lint](#dependency-metadata) is also warning-only
in the native profile; strict defaults retain errors. These are source-derived compatibility checks;
native Windows/MSVC execution is separate.

### Undeclared variables

A global is a module-level variable that every trigger of the module can
read. AAUnlimited also lets a module read a global that another module on the
same card declares, through its dependency list ([native format](native-format.md)
N3, N4). That support was never finished and almost no module uses it, so this
language does not resolve dependencies: a module uses only the globals it
declares, and a variable it never declares is undefined:

- Decompilation keeps the reference raw (`raw_expression int 2 { variable "x"; }`)
  and reports `UNDEFINED_VARIABLE` as a warning, with help naming the
  declaration: `declare it in this module: global x: int = 0;`.
- Validation and compilation report it as an error with the same help; the
  editor offers the declaration as a quick fix. It uses the zero value of the
  reference's type (`0`, `false`, `0.0`, `""`).

Declaring the global makes the module work on its own. On a card that already
has a global with that name, AAUnlimited keeps the card's value. The
declaration also adds the global to the compiled module, so the output is no
longer byte-identical to the original binary.

## Acknowledging Native Hazards

A strict error that reports a known AAUnlimited hazard can be acknowledged in
source, so a module that relies on the native behavior still compiles:

```text
trigger "NPC Flag" {
  on NPC_AFTER_RESPONSE;
  @allow(REVIEWED_VALUE_TYPE_MISMATCH)
  if (Context.NpcCurrentResponse == 0) {
    Notification("answered 0", true);
  }
}
```

An `@allow(CODE, ...)` attribute prefixes a statement (at any depth), event,
local, trigger, trigger import, macro, trigger template or the module
([grammar](grammar.md#acknowledged-hazards)). It covers a finding whose location,
or one of whose expansion origins (a macro call, a trigger import), lies inside
that item. The innermost covering attribute is the one used. A covered error is
reported as a warning with the note `acknowledged by @allow(CODE) at FILE:LINE:COL`;
nothing is hidden and the module compiles. The attribute is source-only: it
changes no SIR or binary output.

Only codes in the language policy's `acknowledgeable` list are accepted
([metadata](metadata.md#acknowledgeable-codes)). The shipped list is
`REVIEWED_VALUE_TYPE_MISMATCH`, `NATIVE_DEFECTIVE_EXPRESSION` and
`EXPRESSION_METADATA_RETURN_TYPE_MISMATCH` (INT/100). Type, scope, arity and
dependency findings cannot be acknowledged.

Findings about the attribute itself:

| Code | Severity | When |
| --- | --- | --- |
| `NATIVE_HAZARD_ALLOWED` | warning | every attribute code that acknowledged a finding: bypassing a hazard is not recommended; fix the problem and remove the `@allow` |
| `ALLOW_NOT_PERMITTED` | error | the code is not in the policy list |
| `UNUSED_ALLOW` | error | the code acknowledged nothing, for example after the hazard was fixed or once an upstream fix removes the finding; an outer attribute whose finding an inner one already covers is also unused |

`UNUSED_ALLOW` needs a complete validation and is not reported for attributes
inside macro or template definitions, whose findings depend on where they are
expanded. A definition is validated on its own, without a call site, so a
definition-time error such as `Text.Replace`'s defect needs the `@allow` inside
the definition; an event-dependent finding appears only at an expansion and is
covered by an `@allow` at the call site or inside the definition.

`decompile` inserts `@allow(CODE)` before the smallest statement, event or local
that contains each acknowledgeable error (an `if`/`else if` chain counts as one
statement) and reports the acknowledged warnings, so a real module with a known
hazard recompiles byte-identically. Remove the attribute once the module no
longer depends on the hazard.

## Typed Statement Macros

Version 7 adds typed statement macros outside the module:

```text
macro "update_points" {
  param seat card;
  param target card;
  param "love" int;
  param "like" int;
  param "spare" int;
  seat.SetPoints(target, ToFloat(love), ToFloat(like), 0.0, 0.0, ToFloat(spare));
}

module "Points" {
  trigger "Conversation" {
    on CONVERSATION_END;
    update_points(ThisCard, Context.NpcTalkTarget, 100, 200, 600);
    update_points(TriggeringCard, Context.NpcTalkTarget, 100, 200, 600);
  }
}
```

Seat/target references are `card`; use explicit numeric conversions where native
actions need floats. See [the complete corrected example](../examples/macros.aa2m).
Definitions can appear before or after exactly one module and can call other
macros. Names must be ordinary non-keyword identifiers; macro lookup is
case-insensitive, while formal references are case-sensitive.
All parameters are required and use `card`, `int`, `bool`, `float`, or `string`.
Calls pass exactly one typed argument per parameter in declaration order,
require a semicolon, and cannot have child or slot blocks. A macro with
no parameters accepts `name();`. Native expression calls retain
their own namespace; macros return no expression. Macro/action name collisions
under the operation policy are rejected.

Actual expressions bind in the caller's ordinary variable scope. Raw-containing
actuals also undergo strict semantic checks before substitution can discard them;
unused raw arguments cannot hide invalid references or signatures. Substitution
duplicates an expression at every formal use: `Math.RandomInt(...)` passed to a
twice-used formal is evaluated twice; an unused argument is type-checked but
never evaluated. Macro calls do not insert temporary variables or conversions.
Definition-intended built-ins bind with only formal variables in scope, so a
caller variable cannot change their meaning. Pass caller state explicitly.
`variable("formal")` can name a formal, but other variable references, raw
variable payloads, assignments, and for-loop targets are forbidden in bodies.
Native/raw Set Variable and For Loop actions are also forbidden. Break/continue
can only target a loop in that same definition, including mapped/raw controls.

Macro bodies contain statements, with no module, trigger, event, variable, or
nested macro declarations. Parameters precede statements. All definitions are
validated, including unused bodies and call cycles; unused definitions emit no
records. Source validation retains unused-body warnings. Expansion preserves
typed identities, grouping, raw recovery, branches, and children. Binary data
contains the expanded native actions; decompilation produces self-contained
expanded source and cannot recover macro definitions or call boundaries.

For staged use, `parse_source_unit` returns a `SourceUnit` with `.module` and
`.macros` (and version 8 `.imports`/`.templates`); `bind_source_ast` accepts either that unit or
an ordinary `SourceModule`. `parse_source_ast` remains module-only and reports
`MACRO_UNIT_REQUIRED` for definitions. Bound modules expose definition warnings
in `.diagnostics`, alongside diagnostics from raw actuals; validation APIs merge
them with emitted-module diagnostics.

Macro bodies see top-level and library [constants](#compile-time-constants)
(`Prefix + text`) but not constants declared inside a module.

## Library Imports

Version 8 adds `.aa2mi` source libraries. A library contains top-level imports,
macros, trigger templates, and (version 13) constants, without a module. Empty libraries are valid. A module source may
place imports and macros before or after exactly one module:

Save this complete example beside `examples/library_imports.aa2m`, so
`libraries/debug.aa2mi` resolves from `examples/`:

```text
import "libraries/debug.aa2mi";
module "Imported" {
  trigger "Conversation" {
    on CONVERSATION_END;
    debug(ThisCard.FullName + " is naive");
  }
}
```

Imports require a path ending in `.aa2mi` (case-sensitive), resolve relative to
each importing file, and never become `depends_on` records. The CLI resolves
the root's imports from its directory. Filesystem identities use the host's
real paths and case normalization; repeated imports, symlinks, and diamonds
deduplicate by identity. Cycles fail. Prefer `/` separators for portable paths.
Imports perform no downloading or runtime loading.

All root and library definitions share one transitive operation namespace.
There are no private exports, qualification, or order-dependent overrides.
Macro names retain case-insensitive lookup; distinct definitions with the same
name fail even when unused. All definitions and their bodies validate, while
only invoked expanded statements enter output. Definitions in any loaded unit
can call any macro in the operation namespace. Decompilation yields expanded
source that recompiles without libraries.

Text APIs require `import_base=...` or `source_resolver=...`, directly or in a
`SourceContext`. A diagnostic filename alone grants no filesystem access. These
options conflict with each other; explicit options must match a supplied context.
`FileSourceResolver(base)` is the standard provider. A custom `SourceResolver`
implements `resolve(path, *, importer) -> str` and
`read(identity, *, max_chars) -> str`: root importer is `None`, nested importer
is the canonical identity, and reads must stop at `max_chars + 1` characters.
Resolve returns a stable, nonempty identity before any read. UTF-8/filesystem
failures become input diagnostics; a resolver's `ValueError` indicates an invalid
path. Other provider programming exceptions propagate.
Providers control access and path semantics. Operation caches reset on every
parse/compile/validation, including with a reused context, so file edits are seen.

`parse_library_source` or `parse_source_unit(..., kind="library")` parses a
library without reading imports. Its `SourceUnit.module` is `None`; `.imports`
retains located import records. `validate_source(..., source_kind="library")`
validates all definitions and imports through the same binder with an empty
internal module. `parse_and_validate_source` returns `None` for the model in
library mode, including on success; inspect the validation result for errors.
Compilation and direct binding require a module unit. CLI `validate lib.aa2mi`
selects library validation; CLI `compile` rejects `.aa2mi` inputs with
`LIBRARY_COMPILE`, while text compilation always requires a module. Module-only
`parse_source_ast` reports `IMPORT_UNIT_REQUIRED` for imports. Imported syntax,
binding, and semantic errors retain library locations and related import notes.

Graph limits are inclusive: `max_import_files=128` unique imported libraries
(root text is separate), `max_import_depth=32` edges on the longest import path,
and `max_total_source_chars=16_777_216` characters in root plus unique libraries.
File/depth checks precede reads; reads use the remaining aggregate/per-file
character budget plus one. The graph also shares an aggregate AST `max_nodes`
budget and the existing macro preparation/expansion budget. Cached diamonds
still count their longest depth. CLI options are `--max-import-files`,
`--max-import-depth`, and `--max-total-source-chars`. Graph failures use
`IMPORT_FILE_LIMIT`, `IMPORT_DEPTH_LIMIT`, `IMPORT_SIZE_LIMIT`, or
`SOURCE_NODE_LIMIT`; path/access failures use `IMPORT_PATH`,
`IMPORT_RESOLVER_REQUIRED`, `IMPORT_READ_ERROR`, or `IMPORT_ENCODING`.
`SourceImportError` carries input diagnostics for resolver/library failures;
validation returns them and compilation wraps them in `CompileError`.
Library constants join the same namespace: duplicates fail even when unused (`DUPLICATE_CONST`).
Library modules fail with `LIBRARY_MODULE`; missing module roots use
`MODULE_REQUIRED`. `import` and `slot` are reserved, with longer prefixes still valid.

## Trigger Templates

Libraries declare reusable triggers with required typed slots:

```text
trigger "Init" {
  slot "name" string;
  on CARD_ADDED;
  if TriggeringCard == ThisCard {
    ThisCard.SetBool(name, ThisCard.GetBool(name, true));
  }
}
```

A module instantiates an imported template at that item's position:

```text
import.trigger "Init" "Initialize" {
  slot "name" = "Naive";
}
```

The second quoted string is an optional output trigger name; omit it to keep
`Init`. The binding block is required, including `{}` for a zero-slot template.
There is no trailing semicolon. Template lookup and output names are exact,
case-sensitive strings. Templates and macros occupy separate namespaces.
Each instantiated name must differ from every ordinary trigger and other
instantiation in the module, including later items. Repeated instantiation is
allowed with distinct names. Imported unused templates emit no trigger records.
See [the complete nested-library example](../examples/library_imports.aa2m).

Slot declarations precede events, locals, and statements. Names must be ordinary
non-keyword identifiers, even when quoted; types are `card`, `int`, `bool`,
`float`, or `string`. All slots are required, without defaults or implicit
conversions other than [card](#cards) widening and literals as cards.
Bindings may use quoted names or identifiers and can appear in any order; missing,
extra, duplicate, or wrong-case names fail. Actual expressions bind in module
global/native scope, with no access to ordinary trigger locals or template locals.
They may use native calls or raw recovery expressions with the exact slot type.
Raw variable payloads in actuals must reference declared module globals with
their declared types; they cannot capture a template local or an undeclared name.
Repeated slot uses repeat runtime evaluation; unused actuals type-check and emit
nothing. Slots are values and cannot be assignment/for-loop targets, including
native or raw assignment-target actions. Raw variable payloads cannot name slots;
use readable references to slots inside raw parameter lists.

Template events, local defaults, and statements bind once in isolated slot/local
scope. All template locals are visible throughout the definition, preserving
declaration order. Caller globals cannot capture definition-intended native names.
Explicit references to variables outside the template fail; pass them via slots.
Slots cannot share names with locals. Locals may be read/written, including by
assignments, for loops, and native/raw target actions. Raw variable references
must name a declared template local with its declared type. Loop control requires
a loop inside the template; nested macros retain their own definition-local rules.
Complete local visibility does not promise safe runtime default evaluation order.

When a template local conflicts with a module global, instantiation renames that
local and all its bound reads/writes to the first unused `_aa2m_local_N` name
(starting at zero in declaration order). Existing globals and template locals
reserve those names. Noncolliding names remain intact. Caller-bound slot actuals
keep their original global references. This makes native global-first lookup
preserve the template's local intent; each trigger still has its own local scope.
Native identities, raw provenance, exact float bits, nested GUI children, empty
branches, event/default vectors, and trigger ordering survive expansion.

All templates validate, including unused bodies, events, locals and nested macro
calls. Unused definition warnings remain visible. Duplicate template names and
slot/local declarations fail. Instantiation diagnostics retain definition, slot,
actual and invocation origins; emitted semantic errors point to their library
or actual location with related invocation notes. Expansion shares the macro
aggregate work budget, with `TEMPLATE_EXPANSION_LIMIT` on template preflight
failure. Template preparation counts complete trigger HIR; instantiation counts
substituted expressions per occurrence and checks combined depth before cloning.
All expanded behavior enters ordinary SIR; decompilation reconstructs expanded
triggers without templates, slots, or libraries.

Template diagnostics include `TEMPLATE_LIBRARY_ONLY`, `TEMPLATE_NAME`,
`DUPLICATE_TEMPLATE`, `TEMPLATE_SLOT_NAME`, `TEMPLATE_SLOT_TYPE`,
`DUPLICATE_TEMPLATE_SLOT`, `TEMPLATE_SLOT_LOCAL_COLLISION`, `TEMPLATE_CAPTURE`,
`TEMPLATE_SLOT_WRITE`, `TEMPLATE_SLOT_RAW_REFERENCE`, `TEMPLATE_LOOP_SCOPE`,
`UNKNOWN_TEMPLATE`, `MISSING_SLOT`, `UNKNOWN_SLOT`, `DUPLICATE_SLOT_BINDING`,
`TEMPLATE_TRIGGER_NAME`, and `TEMPLATE_TRIGGER_NAME_COLLISION`. Ordinary type,
declaration, and source-budget diagnostics also apply. Slots belong to templates;
macro calls continue to use positional typed parameters only.

Template bodies likewise see top-level and library constants, not module
constants; `import.trigger` slot actuals are module expressions and may use
module constants.

## Control Flow

```text
if condition {
  action();
} else if other_condition {
  other_action();
} else {
  fallback_action();
}

loop {
  continue;
}

for counter from 0 to 3 {
  Notification("Iteration");
}
```

These constructs compile to nested GUI-action records. Runtime flattening and
jump generation remain AAUnlimited responsibilities. A `for` target is a
declared `int` or [`card`](#cards) variable; for a card target the start is a
card or a literal (`for seat from 0 to 25 { seat.SetVirtue(1); }`).

Version 5 retains empty branches: `if true {} else {}` produces separate IF
and ELSE records, while `if true {}` produces only IF. Each `else if` also
produces a separate sibling record. Conditions must be `bool`.

For individual serialized branches, use uppercase standalone forms:

```text
ElseIf false {
  Notification("Standalone conditional branch");
}
Else {
  Notification("Standalone fallback branch");
}
Else;
```

`Else;` and `Else {}` each preserve one empty ELSE record. Decompilation uses
`Else;` for a standalone empty branch and lowercase attached clauses for a
contiguous, compatible IF/ELSEIF*/ELSE sequence. Extra, orphaned, or interrupted
branches remain standalone. Raw provenance, hidden branch actions, or missing
or incompatible registry signatures require `raw_action` recovery. Formatting
never changes sibling order or children. Ordinary actions still need
parentheses; `ElseValue()` remains an automatic registry alias.
The reserved `ElseIf` spelling requires a block; the ordinary registry alias
is `ElseIfValue(condition)` and can use a block or semicolon.
Raw provenance is a source-only annotation honored when formatting a model;
binary decompilation chooses readable or raw forms from the wire fields and
operation metadata because that annotation is not serialized.

## Exact Serialized State

Concise globals use default runtime state:

```text
global enabled: bool = true;
```

Use the explicit form when current state or initialization differs:

```text
global counter: int {
  default 0;
  current 1;
  initialized true;
}
```

## Raw Recovery Forms

Unknown IDs and metadata-ambiguous records use raw productions in the same
language:

```text
raw_action 9002(raw_expression type 77 9004 { parameters [ ]; });
raw_expression int 3 {
  named_constant int 7;
}
```

Raw forms preserve numeric IDs, type scopes, payload branches, and nested
children independently of metadata names. Version 9 checks every raw event,
action and expression with the same strict semantic validator as readable/model
records. Unknown registry references, undefined variables, bad signatures,
invalid assignment/loop targets and type mismatches fail ordinary validation
and compilation. This includes raw descendants and unused local/imported macro
and template definitions. Valid known raw records still compile. Raw forms do
not apply source action defaults; structural writer constraints still apply.

## Recovery Limits

The formatter accepts a module model, not a `DecodeResult`. Trailing bytes are
reported separately by `decode_module` and are not retained in the model, so
they are outside source round trips. The native loader does not check trailing
bytes ([native format](native-format.md#no-header-no-trailing-byte-check)); the
report is this tool's hardening. The reader normalizes any nonzero boolean
byte to `true`, and the writer emits canonical `0` or `1`; byte identity does
not cover noncanonical boolean encodings.

`encode_module` applies model and structural writer constraints without running
full semantic validation, so some malformed-but-writable models can be
encoded. `validate_module` and `compile_module` default to strict authoring
checks; an explicit native profile uses the checks described above. Binary
recovery uses decode -> encode. It does not prove executable validity; invalid recovered source fails
`validate_source` and `compile_source`. The formatter fails explicitly for
invalid or unknown global/local declaration types and for mismatches the source
grammar cannot preserve. Numeric type IDs remain available in raw expressions.

## CLI

These paths are placeholders for your inputs and outputs. Run from the
synchronized source-tree environment; the README quick start supplies an
existing example and temporary output paths.

```bash
python -m aa2modulus validate source.aa2m
python -m aa2modulus compile source.aa2m --output MODULE
python -m aa2modulus decompile MODULE --output recovered.aa2m
python -m aa2modulus inspect MODULE
```

There is no separate canonical or friendly source mode and no `--canonical`
flag. Decompilation always emits unified source, using raw forms when readable
metadata projection would not preserve the serialized IR.

Formatting reports `FormatError` when a serialized global or local type
mismatch or unsupported declaration type has no source production that
preserves it. Source validation checks raw records strictly.

Exit codes are `0` for success, `1` for input errors (including unsupported
source projection), `2` for command usage errors, and `3` for registry/policy
configuration failures. `validate`, `compile` and `decompile` print diagnostics
and a closing summary line to stderr; stdout carries only the primary output
(`valid: ...`, `compiled: ...`, recovered source, or `decompiled: ...`).
`compile` fails without creating/overwriting output and prints warnings on success. `decompile` writes
recovered source to stdout (or the requested file), locates its diagnostics in
that text (named by the `-o` path, or `<stdout>`), reports trailing bytes as a
`TRAILING_BYTES` warning, and returns `0` on recovery success even when
semantic errors mean ordinary compilation will fail in the selected environment.
Decode (`DECODE_ERROR`), unsupported projection and write failures return `1`.
`inspect` is permissive by default; `--strict` returns `1` for validation errors
or trailing bytes. Its report lists diagnostics on stdout with a readable
breadcrumb and hex offset instead of a source location.

Inspection uses native GUI labels and keeps parameter types/IDs, diagnostics,
and nested action order visible. Exact known operator templates with matching
signatures use precedence-aware grouping: `If (ThisCard == TriggerCard) then`
has one condition wrapper, while `(a + b) * c`, `a - (b - c)`, and right-nested
boolean or float operations retain their tree grouping. Nested comparisons stay
grouped. Unknown records, malformed signatures, and arbitrary GUI templates
retain conservative rendering. This display does not change module fields or
serve as compilable `.aa2m` source; use `decompile` to recover source.

`inspect --validation-profile strict|native` selects the checks independently
of `--strict`, which controls the exit status. Source commands keep strict
authoring semantics; the native option is inspection-only.
`inspect --strict --validation-profile native` succeeds when dependency metadata
warnings are its only findings; unresolved variables and other errors still fail.

See the executable [quick start](../README.md#quick-start) for a complete
workflow using the maintained notification example.

### Diagnostic output

`validate`, `compile`, `decompile` and `inspect` accept:

- `--diagnostic-format human|short` (default `human`). `human` shows the
  headline, a `-->` location, the source line with carets under the span,
  related locations as `note:` blocks with their own snippets, and `= note:` /
  `= help:` lines. `short` prints one `file:line:col: severity[CODE]: message`
  line per finding (`file@0xOFFSET:` when it has only a binary location) plus
  one `file:line:col: note: ...` line per related location; use it for grep,
  problem matchers and tests.
- `--color auto|always|never` (default `auto`). `always` and `never` win.
  Under `auto`, a non-empty `NO_COLOR` disables color, a non-empty
  `FORCE_COLOR` other than `0` enables it, `TERM=dumb` disables it, and
  otherwise only a terminal is colored; piped or redirected output is plain.
  On Windows, color needs a console with virtual-terminal processing.
- `--verbose` adds binary evidence: the hex offset and the structural path.

```
warning[REVIEWED_VALUE_TYPE_MISMATCH]: Context.NpcCurrentResponse only reads an int from event data during NPC_RESPONSE; during NPC_AFTER_RESPONSE AAUnlimited returns `false` instead of an int, so this reads unspecified bits that can change between reads
   --> recovered.aa2m:123:13
    |
123 |         if (Context.NpcCurrentResponse == 0) {
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^
    |
    = note: in trigger "NPC Flag"
    = note: acknowledged by @allow(REVIEWED_VALUE_TYPE_MISMATCH) at recovered.aa2m:122:9

warning[NATIVE_HAZARD_ALLOWED]: @allow(REVIEWED_VALUE_TYPE_MISMATCH) bypasses a known AAUnlimited hazard; bypassing it is not recommended
   --> recovered.aa2m:122:16
    |
122 |         @allow(REVIEWED_VALUE_TYPE_MISMATCH)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |
    = help: fix the underlying problem, then remove this @allow

decompiled MODULE -> recovered.aa2m with 2 warnings
```

Headlines name built-ins by their canonical source spelling
(`Context.NpcOriginalResponse`, `Notification`, `CARD_ADDED`), assignment and
`` `for` loop`` by syntax, and targets without a source name by raw form
(`raw_action 108`, `raw_expression int 19`). When the AAUnlimited GUI label
differs, a note gives it for searching the native editor:
`= note: native name: 'Npc Original Response'`.

Snippets expand tabs, count East Asian wide characters as two columns, and
clip long lines around the span. Columns in locations are code points.
A finding with only a binary location shows the breadcrumb (for example
`trigger "NPC Flag" › If (…) then › parameter 1: … › return type`) in place of
a snippet.

## API Diagnostics

The Python entry points below describe internal use and maintainer tooling. The
product ships as a standalone CLI and LSP server; Python embedding is not a
supported compatibility contract.

Syntax parsing raises `SourceParseError`; binding raises `SourceBindingError`;
source library resolution raises `SourceImportError` for located input failures.
Source budget failures raise `SourceLimitError`, carrying a `Diagnostic`.
`validate_source` returns a `ValidationResult`, and
`parse_and_validate_source` also returns the model when parsing/binding succeeds.
Budget checking stops at the first error. A failed parse reports every
independent syntax error: the parser's own first error comes first, unchanged,
then recovery resumes after each fault at the next `;`, `}`, declaration keyword
or line, skipping whole `{ ... }` blocks whose header failed. At most one error
is kept per statement (between `;`, `{` and `}`), a fault right after resuming
is dropped as part of the previous one, and after any error a stray `}` or a
missing `}` at the end of the file is not reported, since it is nearly always
caused by the earlier error. Beyond `max_syntax_errors` one
`SOURCE_SYNTAX_ERROR_LIMIT` error ends the list. Literal and structural errors
found after a successful grammar parse (an out-of-range integer, a missing
module declaration) stay single, and a library that fails to parse during an
import reports only its first syntax error; validating the library itself
reports all of them. Binding does not run while any syntax error exists.

Syntax and name errors carry a `help` line, and an exact fix where one exists,
for common habits from other languages:

| Written | Help | Fix |
| --- | --- | --- |
| `=` where a comparison fits (`if (y = 3)`) | use `==` to compare | `==` |
| `x += e`, `x -= e`, `x *= e`, `x /= e`, `x++`, `x--` | write `x = x + e;` | the rewrite, with `e` in parentheses unless simple |
| `a and b`, `a or b` | use `&&` / `\|\|` | the operator |
| `not x` | use `!(condition)` | none (`!` binds tighter) |
| `elif`, `elseif`, `elsif` | write `else if condition { ... }` | `else if` after `}` |
| `let x = e;`, `global x = e;` | add a type after the name | none |
| `'text'` | strings use double quotes | `"text"` |
| `while (c) { ... }` | write `loop { break if !(c); ... }` | the loop header, body kept |
| `while c {`, `return`, `function`, `def`, `fn`, `switch` | what to use instead | none |
| an unclosed `/*` | the comment is never closed | none |

These words are not reserved: a macro or variable named `while` still works,
and the name hints appear only when the name is otherwise unknown.

Binding reports every
independent error: each constant, macro, template, global, trigger, local, event
and statement is checked on its own, in source order. A failed declaration
(`let x: int = bad;`, a global or a constant) stays declared with its type, so
its uses report nothing further; a macro or template whose definition fails is
reported once and its calls and instantiations report nothing. Inside one
statement, a call, member call, event, action or macro call with a single
candidate reports every failing argument (nested calls included); overloaded
calls and operators report the error of their closest candidate only. Duplicate
constants, constant cycles, trigger-name collisions and definition-order errors
still stop binding, keeping the errors found before them.
`SourceBindingError.diagnostic` is the first error and `.diagnostics` holds all
of them. Semantic validation runs only once binding is clean, so its findings
(such as `NATIVE_DEFECTIVE_EXPRESSION`) appear after the binding errors are
fixed. Globals are checked once even if the module has no triggers.

`validate_module` checks SIR under the selected strict/native profile regardless
of raw provenance. It reports semantic diagnostics without modifying the model.
Use the structural parse/encode or decode/encode workflows described in
[recovery limits](#recovery-limits) to retain invalid but representable data.

`compile_source` and `compile_module` raise `CompileError` with structured
diagnostics for input failures, including writer constraints that validation
alone does not check. Wrong return types use `SOURCE_TYPE_MISMATCH`; wrong call
argument counts use `EXPRESSION_ARITY`. Nested failures point to the offending
expression. Writer failures point at the source node they came from.
Catalog configuration
errors raise `MetadataError` separately, and programming errors propagate.
Macro binding errors point to a definition or offending actual expression.
`Diagnostic.related` holds `RelatedLocation(span, message)` notes for formal
declarations, definitions, and invocation chains; CLI rendering prints them as
located notes. Expanded nodes retain these nonserialized origins in their spans.
`Diagnostic.notes` holds unlocated context lines and `Diagnostic.help` a fix when
one is known; `Diagnostic.fixes` holds the concrete `SourceFix(title, span,
replacement)` edits behind that help, which editors apply and printed forms
never show. `path` (structural) and `offset` (binary) are evidence fields that
the printed headline omits; `str(diagnostic)` is the `short` form
`file:line:col: severity[CODE]: message`, or `file@0xOFFSET: ...` when a finding
has only a binary location, followed by one `file:line:col: note: ...` line per
related location.

`decompile_module(data, filename=..., source_filename=...)` locates its
diagnostics in the recovered text: `source_filename` (default `<decompiled>`)
names that text, and each diagnostic keeps its binary `offset` and `path`.
Recovery is lossless, so reparsing the recovered text yields nodes at the same
structural paths as the decoded module; the decompiler maps each finding to the
deepest such node. A raw fallback whose node also has a semantic error is folded
into that error as a note instead of a separate warning.

`decompile_module` returns `DecompileResult(source, decoded, diagnostics)`.
`.decoded` is the existing `DecodeResult`; `.diagnostics` is a tuple of shared
`Diagnostic` values. Each emitted raw record/expression reports `RAW_FALLBACK`
with a concrete reason and input location, including descendants forced raw
by an enclosing expression. Reasons include unknown identity, unresolved name,
declaration/signature mismatch, ambiguous source spelling, explicit raw
provenance and enclosing syntax. Valid policy-driven raw output produces warnings
without semantic errors. Strict validation checks the original SIR independently
under the supplied metadata.
Use `filename` for binary input names (default `<binary>` or the context filename).
Library calls never print diagnostics. `format_module` remains a pure string
utility with unchanged projection rules.

## Source Resource Limits

Source text APIs accept `source_limits=SourceLimits(...)`. A reusable
`SourceContext` carries the same immutable options; explicitly supplied options
must equal the context's options. Stage budgets are checked independently;
definition work and import graph budgets cap the aggregate operation.

| Option | Default | Meaning |
| --- | --- | --- |
| `max_source_chars` | 4,194,304 | Unicode code points in source text, checked before parsing. |
| `max_nodes` | 200,000 | Lark trees plus token leaves, or AST/HIR node records, per stage. Spans, registry records, scalar fields, and tuple containers are excluded from AST/HIR counts. |
| `max_binding_work` | 200,000 | Aggregate expression visits and overload attempts for one operation, including rejected candidates; independent of retained-node and expansion budgets. |
| `max_binding_errors` | 100 | Independent binding errors reported for one operation (minimum 1); beyond it binding stops with one `SOURCE_BINDING_ERROR_LIMIT` error. |
| `max_syntax_errors` | 25 | Syntax errors reported for one failed parse (minimum 1); beyond it one `SOURCE_SYNTAX_ERROR_LIMIT` error ends the list. |
| `max_syntax_depth` | 256 | Tree/AST/HIR record levels along a path, with the root at one. Token leaves and tuple containers add no depth. Groups and raw payload wrappers contribute record levels. |
| `max_nesting_depth` | 64 | Combined statements and expressions along an AST/HIR path, including leaves and raw expression records. Groups, declarations, events, and payload records such as `SourceRawParameters`/`BoundRawParameters` add no nesting. |
| `max_expansion_nodes` | 200,000 | Aggregate HIR record work for preparing all macro bodies/template triggers and preflighting each instantiation; repeated actual trees count per occurrence. |
| `max_macro_depth` | 64 | Longest definition call chain, including its root, even for unused/empty bodies; supported ceiling 128. |
| `max_import_files` | 128 | Unique imported library identities, excluding root text. |
| `max_import_depth` | 32 | Longest import path in edges, including cached diamond subgraphs. |
| `max_total_source_chars` | 16,777,216 | Unicode characters across root text and unique imported libraries. |

Attached and standalone ElseIf/Else records count as statement nodes. An
attached branch is a child of its If record, so its body or condition adds
nesting below both records. Each branch also contributes one node and one
record level to the AST/HIR budgets; its own source span locates budget errors.
SourceUnit, import, macro, template wrapper, instantiation site, slot binding,
and formal records count as AST nodes; positional macro calls use
ordinary SourceAction records. Macro definitions and calls also count as source
nesting. Formals and the unit wrapper add no nesting. Ordinary `SourceModule`
inputs retain their counts.
Macro bodies bind once in dependency order. Aggregate expansion work includes
fully expanded prepared bodies and every nested/emitted substitution preflight;
an empty body costs zero work. Preflights check saturated node counts and
combined caller/template/actual depth before cloning. Final HIR budgets still
apply. Budgets reset per operation, and the context stores no macro cache.

Bounds are inclusive and accept nonnegative integers, including zero. Character
and node bounds can be raised. Syntax depth has a supported ceiling of 512 and
statement/expression nesting has a ceiling of 128, keeping the remaining
recursive binding, lowering, validation, and writing within supported depths.
Invalid option types raise `TypeError`; negative or unsupported depth values
raise `ValueError`. The eight shipped fixtures fit the defaults with substantial
headroom. These are compiler resource choices, not binary format restrictions.

Tree inspection and AST transformation are iterative. Syntax depth comes from
the parsed tree: parentheses or braces inside strings and comments do not count.
`parse_source_ast` checks AST budgets after transformation; `bind_source_ast`
checks supplied AST before binding, and
`lower_bound_module` checks supplied HIR before lowering. Direct AST/HIR inputs
have node/depth budgets but no source-text character count. HIR checks also
cover defaults inserted during binding. `ReaderLimits` and `WriterLimits` remain independent;
`compile_source(..., limits=WriterLimits(...))` still controls binary writing.

Over-budget inputs use `SOURCE_SIZE_LIMIT`, `SOURCE_NODE_LIMIT`,
`SOURCE_DEPTH_LIMIT`, `SOURCE_NESTING_LIMIT`, or `SOURCE_BINDING_WORK_LIMIT`.
The CLI exposes `--max-binding-work` for the aggregate binding budget,
`--max-binding-errors` for the binding error cap and `--max-syntax-errors` for
the syntax error cap.
Size errors point to line 1,
column 1; tree errors use the offending tree/token position. Record errors use
the node's span or the closest available enclosing span, falling back to the
context filename at line 1, column 1 for unlocated inputs. Validation APIs return
these diagnostics;
`compile_source` wraps them in `CompileError`. Parsing, binding, and lowering
entry points raise `SourceLimitError` directly.
Macro work and call-chain overflow use `MACRO_EXPANSION_LIMIT` and
`MACRO_DEPTH_LIMIT`. Macro names/signatures/calls use `MACRO_NAME`,
`DUPLICATE_MACRO`, `MACRO_ACTION_COLLISION`, `MACRO_PARAMETER_NAME`,
`DUPLICATE_MACRO_PARAMETER`, `MACRO_PARAMETER_TYPE`, `MACRO_ARITY`,
and `MACRO_CALL_BLOCK`. Scope failures use `MACRO_CAPTURE`,
`MACRO_PARAMETER_WRITE`, or `MACRO_LOOP_SCOPE`; recursion uses `MACRO_CYCLE`.
Ordinary unknown-expression/type diagnostics remain applicable to actuals and
definition bodies. Forbidden declarations are syntax errors.

```python
from aa2modulus.app.compile import validate_source
from aa2modulus.context.limits import SourceLimits
from aa2modulus.context.operation import SourceContext

context = SourceContext.create(
    filename="small.aa2m",
    source_limits=SourceLimits(max_source_chars=10_000, max_nesting_depth=32),
)
result = validate_source('module "Small" {}', context=context)
assert result.is_valid
```

CLI `validate` and `compile` expose `--max-source-chars`, `--max-source-nodes`,
`--max-syntax-depth`, and `--max-source-nesting`. Over-budget input returns exit
`1` through the usual diagnostic output; invalid limit options return exit `2`.
Compilation writes output only after successful compilation. CLI text reads
stop after the character budget plus one character, enough to report an
oversized file without loading it in full.
`--max-macro-nodes` and `--max-macro-depth` select the macro work/depth bounds;
macro compilation failures also leave output files untouched.

## Versioning

- Changes to syntax, source-to-SIR meaning or semantic acceptance update the
  source language version. Version 9 tightens raw validation without changing
  grammar productions, policy/registry schema or binary fields. Version 11 adds
  postfix receiver calls, `member_forms` and policy schema v4. Version 12 makes
  registered namespace roots case-sensitive (policy roots start with an uppercase
  ASCII letter and are unique ignoring case) and a target with a canonical
  spelling accepts only that spelling and its aliases (native fallbacks are
  rejected with a hint). Version 12 also makes the member form the only spelling of
  the 213 card-first built-ins (property reads `coach.Virtue`, bare built-in
  receivers `ThisCard.Virtue`); the `Character` root and the card-first
  `Npc.*`/`CardStorage.*` names are retired. Policy schema v5
  (TOML, no hash guards) changes the policy file format only; source meaning and
  the language version are unchanged.
- Version 13 adds `const` declarations and `const("Name")` references
  (`const` becomes reserved) without changing serialized output.
- Version 14 makes `TriggeringCard` (native `int:9`) an unqualified core name;
  `Context.TriggeringCard` is retired. `ThisCard` and `TriggeringCard` become
  protected names (policy schema v6, `protected_names`) that variables and
  constants can no longer shadow. Serialized output is unchanged.
- Version 15 adds source-only `@allow(CODE)` attributes that acknowledge known
  native hazards (policy schema v10, `acknowledgeable`). Serialized output is
  unchanged.
- Version 16 adds the source-only [`card`](#cards) type and `Card(...)`
  (`card` and `Card` become reserved). Card roles in policy now type values
  (policy schema v11 adds `[parameter_roles]`); an `int` in a card position is
  an error. Serialized output is unchanged.
- Generated metadata records source revision, generator version, schemas, and
  entry counts in `aa2modulus/metadata/registry/manifest.json`. The editable
  default language policy lives at `aa2modulus/language/policy.toml`;
  it is schema-validated and checked against the registry, but intentionally not
  content-hash locked.
- Raw forms remain the lossless escape for unknown or forward-versioned IDs.
