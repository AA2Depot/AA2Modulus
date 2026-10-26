# Unified `.aa2m` Grammar

Status: unified source language, version 16

The `.aa2m` language has one source surface. It is parsed into a syntax-only
Source AST, bound through metadata and symbols, lowered into the AA2 Serialized
IR, and written using the existing AAUnlimited binary contract.

The source language is readable by default and remains lossless through
explicit raw forms. Raw forms are productions in this grammar, not a second
dialect. Version 16 adds the source-only declaration type `card` and the
conversion `Card(expression)` (see [cards](#cards)); both write `int`. Version 15
adds `@allow(CODE)` attributes that acknowledge known native hazards (see
[acknowledged hazards](#acknowledged-hazards)); they are
source-only. Version 14 makes `ThisCard` and `TriggeringCard` unqualified,
protected built-in names (see [protected names](language.md#protected-names)); no
serialized field changes. Version 13 adds compile-time `const` declarations and `const("Name")`
references (see [constants](#compile-time-constants)); they change no
serialized field. Version 11 added postfix receiver calls such as `actor.AddLike(target, 30)`
for explicitly configured native callables, and version 12 makes them (plus
property reads such as `actor.Virtue`) the only spelling of card-first built-ins;
they lower to the flat native records, and no serialized field changes. Version 10 added checked catalog forms
and verified literal source values through the existing qualified-name syntax.
Aliases merge additively; deliberate native-name overrides require fact guards.
Readable children may appear inside raw records. Version 9's strict raw/definition
validation remains in force; tokens and precedence are unchanged.

Production blocks and expression/statement snippets below describe syntax,
not standalone input files. Complete compilable modules live in
[examples](../examples), starting with [notification.aa2m](../examples/notification.aa2m).

## Lexical Forms

```text
identifier := [A-Za-z_][A-Za-z0-9_]*
builtin-name := identifier ('.' identifier)*
integer    := [-+]?[0-9]+
float      := [-+]?(digits '.' digits? | '.' digits) exponent? [fF]?
string     := JSON double-quoted string, including `\uXXXX` escapes
boolean    := true | false
float_bits := `float_bits(0xHHHHHHHH)` for an exact IEEE-754 binary32 value
```

Whitespace is insignificant. Comments use `//` to end a line or `/* ... */`.
Line comments may end at EOF. Block comments end at the first `*/` and do not
nest; an unterminated block is a syntax error. Comments can separate complete
tokens, while comment markers inside strings are literal text. Comments are
discarded during parsing and are not serialized or recovered by decompilation.
Keywords match complete identifier tokens: names such as `true_flag` and
`breakpoint` remain identifiers. The formatter quotes declaration names that
collide with keywords and uses `variable("name")` for their references and
assignment targets. `const` is a reserved keyword; `const_x` and `constant_x`
remain identifiers, and a quoted `"const"` name is valid. `card` and `Card`
(any case) are reserved too. The reserved words are exactly the grammar's
words, each segment of `import.trigger` included, in any letter case.
A bare reserved word cannot name or assign a variable or constant: quote it,
or write `variable("...")` or `const("...")`.
`aa2modulus editor-data lexicon` prints this lexical surface (words by group,
operators, punctuation, literal patterns and comments) as JSON with its
fingerprint, for editor grammars to test against.

Built-in names may be qualified, for example `ClassStorage.GetInt` or
`Globals.CurrentDay`. Every segment must be a non-keyword identifier. Dots
are contiguous with their segments; whitespace/comments around a dot, empty
segments, and leading/trailing dots are invalid. Qualified names select a
policy-defined built-in, including when a quoted variable has that exact name.
The lexer keeps `name.Member` as one qualified-name token; the binder decides
whether it is a registered static path or a [receiver member](#receiver-calls). The
first segment of a registered path (its namespace root, such as `Context`) matches
case-sensitively; later segments and unqualified built-ins match case-insensitively.
Members read as properties (`coach.Virtue`) or calls (`coach.SetVirtue(3)`); there
is no object model or setter syntax. Variable declarations and assignment
targets still use ordinary identifiers or their explicit quoted/`variable(...)`
forms.

## Module and Trigger Grammar

```text
source-unit := (import | allowed-macro | const)* allowed-module (import | allowed-macro | const)*
library-unit := (import | allowed-macro | allowed-template | const)*
import := "import" string ";"
macro := "macro" name "{" parameter* statement* "}"
parameter := "param" name source-type ";"
module := "module" string "{" module-item* "}"
allowed-macro := allow* macro
allowed-module := allow* module
allowed-template := allow* trigger-template

module-item :=
    "description" string ";"
  | "depends_on" string ";"
  | const
  | "global" name ":" source-type "=" const-value ";"
  | "global" name ":" source-type "{"
        "default" raw-value ";"
        "current" raw-value ";"
        "initialized" boolean ";"
    "}"
  | allow* trigger
  | allow* trigger-import

const := "const" name ":" type "=" const-value ";"
const-value := literal | identifier | const-ref
const-ref := "const" "(" string ")"

trigger := "trigger" string "{" trigger-item* "}"
trigger-item := allow* (event | raw-event | local) | statement

event := "on" builtin-name ("(" expression-list? ")")? ";"
raw-event := "raw_event" integer ("(" expression-list? ")")? ";"
local := "let" name ":" source-type "=" expression ";"
trigger-template := "trigger" string "{" slot-declaration* trigger-item* "}"
slot-declaration := "slot" name source-type ";"
trigger-import := "import.trigger" string string? "{" slot-binding* "}"
slot-binding := "slot" name "=" expression ";"
source-type := type | "card"
type := "int" | "bool" | "float" | "string" | "invalid" | "type" integer
```

`name` is an identifier or a quoted string. Quoted names preserve serialized
variable names that are not valid identifiers. `card` is a declaration type only:
`const` declarations and raw forms take `type`.

`depends_on` declarations retain ordered native metadata strings. Omission writes
an empty dependency vector. They load no modules, supply no globals, and import no
source definitions. Strict semantic validation rejects empty/self/duplicate names
and optionally unavailable names; the native model profile reports these as
warnings. Parsing alone retains invalid records for structural recovery. See
[dependency metadata](language.md#dependency-metadata) for lint and context rules.

Version 8 imports `.aa2mi` libraries. Library units contain imports, macros, and
trigger templates
without a module; module units require exactly one module. `import` is reserved.
Imports expose one transitive definition namespace and deduplicate canonical
identities. All definitions validate; imports add no serialized dependencies.
Resolution requires explicit API access options and uses operation-local graph
budgets. See [library imports](language.md#library-imports) for paths,
visibility, standalone validation, diagnostics, and counting rules.
`slot` is also reserved. Trigger templates are library-only. All slots are
required typed values; bindings use exact case-sensitive slot names. Optional
renaming and instantiation occur only as module items. See
[trigger templates](language.md#trigger-templates) for isolated binding,
local hygiene, repeated evaluation, and errors. Template slots precede every
event, local, or statement; ordinary triggers cannot declare slots.

Global declarations form one module scope. Each trigger has its own complete
local scope, visible in events, local defaults, and statements regardless of
declaration order. Lookup searches globals first, then trigger locals. Duplicate
globals and duplicate locals within a trigger are semantic errors; resolution
uses the first declaration while checking an invalid module. Other triggers'
locals are never visible. Blocks do not introduce declaration scopes. A global
that only another module declares is undefined; see
[globals from other modules](language.md#globals-from-other-modules).

Version 3 replaces incremental local binding with complete-trigger lookup,
matching the pinned native resolver. This defines reference visibility, not
runtime default evaluation order or safe self/cyclic initialization. Serialized
declaration order remains unchanged.

## Acknowledged Hazards

```text
allow := "@allow" "(" identifier ("," identifier)* ")"
```

`@allow` is one token (no space after `@`) and not a reserved word. Attributes
stack and prefix the item that follows: a statement at any depth, an event, a
local, a trigger, a trigger import, a macro, a trigger template or the module.
Imports, constants, globals, `description`, `depends_on`, slots and parameters
take none. Codes are diagnostic codes; which ones are accepted, and the effect,
is in the [language reference](language.md#acknowledging-native-hazards). The
parser keeps each attribute with its own and its item's span in a side table
of the source unit; attributes never reach HIR, SIR or the binary.

## Compile-Time Constants

```text
const Limit: int = 3;
const "With Spaces": string = "text";
const Alias: string = const("With Spaces");
```

A `const` declaration (type `int`, `bool`, `float` or `string`; annotation
required) may appear at the top level of a module or library unit and as a
module item. Its value is a literal, including `float_bits(...)`, or a reference
to another constant, by bare identifier or `const("Name")`. `const(...)` is also
an expression atom and a receiver (`const("LEAD").SetVirtue(3)`); a bare
constant name parses as an ordinary name and the binder resolves it. Global
literal initializers (`global x: int = Limit;`) accept `const-value`; the
`default`/`current` state form stays raw. `const` is reserved, so it cannot be an
unquoted variable, parameter or event name. Constants are not serialized. Scope,
resolution, collisions and diagnostics are in the
[language reference](language.md#compile-time-constants).

## Statements

```text
statement := allow* statement-body
statement-body :=
    action
  | member-action
  | raw-action
  | assignment
  | if-statement
  | standalone-else-if
  | standalone-else
  | loop-statement
  | for-statement
  | "break" ("if" expression)? ";"
  | "continue" ("if" expression)? ";"

action := builtin-name "(" expression-list? ")" (block | ";")
member-action := receiver "." member-name "(" expression-list? ")" ";"
raw-action := "raw_action" integer "(" expression-list? ")" (block | ";")
            | "raw_action" integer ";"
assignment := assignment-name "=" expression ";"
assignment-name := identifier | "variable" "(" string ")"

if-statement :=
    "if" expression block
    ("else" "if" expression block)*
    ("else" block)?

standalone-else-if := "ElseIf" expression block
standalone-else := "Else" (block | ";")

loop-statement := "loop" block
for-statement := "for" name "from" expression "to" expression block
block := "{" statement* "}"
```

Assignments lower to `ACTION_SETVAR` with an `EXPR_VAR` target. Control-flow
statements lower to nested GUI actions; the compiler does not emit runtime jump
instructions.

The compatibility projection mirrors pinned native state lifetimes: conditional
children reset loop state, so a Break/Continue there can be discarded before
native resolution. An inner loop establishes new state; ordinary action children
retain loop state. Source authoring reports `NATIVE_DISCARDED_CONTROL` warnings
and preserves these records. This changes no syntax or source-to-SIR mapping.

Version 5 preserves branch presence explicitly: `if true {} else {}` writes
two sibling GUI actions (IF ID 2 and ELSE ID 4), while `if true {}` writes only
IF. Each attached `else if` writes an ELSEIF action (ID 3), including an empty
body. Conditions require `bool`; blocks retain their complete ordered children.

Uppercase `ElseIf condition { ... }` and `Else { ... }` represent individual
serialized branch actions, including orphaned or unusual sibling sequences.
`Else;` and `Else {}` both write one empty ELSE action; the formatter chooses
`Else;` for a standalone empty action. Lowercase `else if` and `else` attach
only to an `if`. Ordinary actions still require call parentheses; the automatic
registry spelling `ElseValue()` remains an ordinary action alias.
`ElseIf` is now reserved for branch syntax; the automatic ordinary-action
spelling is `ElseIfValue(condition)`, with parentheses and a block or semicolon.

Formatting groups a contiguous IF, zero or more ELSEIFs, and at most one ELSE
only when each record is non-raw, visible under the source policy, and matches
the fixed native signature in the operation's registry. Grouping preserves
every sibling and its children. A terminal ELSE ends the group; extra branches
remain standalone. Raw, hidden, missing-metadata, or incompatible branches use
`raw_action`, and grouping never crosses an intervening record. The same rule
applies independently to every nested child sequence.

## Typed Statement Macros

Version 7 permits definitions before or after exactly one module. Macro names
and formal names must be unqualified non-keyword identifiers, even when quoted
in declarations. Macro lookup and duplicate detection are case-insensitive;
formal references are case-sensitive like variable names.
Formals accept `int`, `bool`, `float`, and `string`, without defaults. Parameters
precede body statements. Modules, triggers, globals, locals, events, and nested
definitions are not permitted in macro bodies. `macro` and `param`
are reserved; longer identifiers with those prefixes remain valid.

A statement call to a declared macro uses `name(expr, ...);` with exact arity
and arguments in parameter declaration order. Its action-style child block is
forbidden, including an empty block. Macros use parameters only; slot blocks
are syntax errors. A zero-parameter macro accepts `name();`. Unknown calls
retain ordinary action lookup. Macro names cannot collide with
visible action names under the operation's registry and policy. Expression
calls remain native expression calls; macros have no returned-expression form.

All definitions, including unused ones, are checked in dependency order.
Recursion/cycles are rejected. A definition binds with only its formal variables
in scope: other bare names select native expressions/constants, and explicit
`variable("formal")` may reference a formal. Caller globals/locals cannot capture
definition-intended built-ins. Non-formal variable references, assignments,
for-loop targets, raw variable payloads, and native/raw Set Variable or For Loop
actions are forbidden in definitions. To read caller state, pass it as an actual.
Break/continue, including mapped or raw controls, require a loop inside their
own definition; nested macros cannot borrow the caller's loop.

Actuals bind in caller scope against formal types, even if unused. Already bound
expression trees replace formal references in typed HIR. Each occurrence has
the actual's runtime evaluation; repeated uses evaluate repeatedly, and unused
actuals produce no evaluation. Native random/Lua/context expressions retain
those semantics. No temporaries or conversions are inserted. Grouping, raw
provenance, children, branch presence, and scoped identities are preserved.
Definition bodies also use ordinary SIR semantic validation; unused-body warnings
are retained. Only invoked expanded bodies enter the module. Decompilation emits
ordinary self-contained source; definition and invocation boundaries are not
serialized. See [the complete example](../examples/macros.aa2m).

## Expressions

Expressions use normal precedence, from lowest to highest:

```text
||
&&
== !=
< <= > >=
+ -
* /
!x
```

Parentheses override precedence. Equality and relational tiers each permit
one operator; comparison chains require grouping. Version 4 separates those
tiers to honor the shipped policy's existing precedence declarations.
Operator tokens, precedence, fixity, and associativity are fixed by the grammar;
policy may choose compatible overload mappings but unsupported syntax edits
raise `MetadataError`. See [the policy contract](metadata.md#fixed-operator-syntax).
Function expressions use calls; built-ins whose first native argument is a card
are members of that card ([receiver members](#receiver-calls)):

```text
Math.RandomInt(1, 6)
ThisCard.Love(Context.NpcTalkTarget)
ThisCard.FullName
ThisCard.GetBool("enabled", true)
```

Zero-parameter expressions use bare names:

```text
ThisCard
TriggeringCard
Context.NpcTalkTarget
Globals.CurrentDay
```

Variables also use bare names. Binding resolves variables before zero-argument
expressions and named constants according to the compiler symbol rules.
Write `Name()` to select a zero-argument expression when a variable of the same
name is in scope. The formatter uses the explicit call in that case and
raw syntax for named constants whose names are shadowed or ambiguous.

`ThisCard` and `TriggeringCard` are protected names (policy `protected_names`,
case-insensitive): a bare identifier declaration of either is `PROTECTED_NAME`,
and bare references and receivers always select the built-in. A serialized
variable with such a name is declared with a quoted name
(`let "ThisCard": int = 0;`) and referenced as `variable("ThisCard")`.

Calls and bare built-in expressions use `builtin-name`. Version 6 uses
case-insensitive policy names and aliases before registry spellings, within
each registry kind and before type/arity filtering. Policy collisions remain
ambiguous unless the existing expression overload rules resolve them.
Registry fallback names come from native record names and their normalized
identifiers, plus native event symbols. Interactive labels that are already
valid source names remain exact aliases; GUI templates are never normalized
into identifiers and their placeholders do not supply source aliases.
Qualified names use policy lookup only and retain their dots. Preferred policy
names control readable output; operator and control-flow syntax keep priority,
and hidden, raw, ambiguous, or unsafe records keep raw recovery. Unqualified
names retain variable-first binding. See [preferred names](metadata.md#preferred-names-and-lookup).

Operators are resolved by operand types and expected result type. There are no
implicit numeric conversions; a `card` widens to `int`.

### Cards

```text
card-conversion := "Card" "(" expression ")"
```

`Card(expression)` is an expression atom and a receiver
(`Card(seat).SetVirtue(1)`). It converts an `int` to the source type `card` and
adds no record. Typing rules are in the [language reference](language.md#cards).

### Receiver Calls

```text
receiver := "variable" "(" string ")" | const-ref | card-conversion | "(" expression ")" | call
          | member-call
          | member-property
member-call := receiver "." member-name "(" expression-list? ")"
member-property := receiver "." member-name
member-action := receiver "." member-name "(" expression-list? ")" ";"
member-name := identifier | qualified-name        // one lexed token, split by the parser
builtin-name := qualified-name | identifier       // also binds as receiver.Member[(...)]
```

A member names an entry of the language policy. The receiver is the first native
argument and the explicit arguments fill the rest in order: `actor.AddLike(target,
30)` calls native Add Like Points with `actor`, `target`, `30`. A member without
explicit arguments that returns a value is a property (`actor.Virtue`, no
parentheses); every other member is a call. Postfix receivers (`variable("x")`, a
parenthesized value, a call result or another member) parse as positioned
`SourceMemberCall`, `SourceMemberProperty` and `SourceMemberAction` nodes; the
property node's `name_span` covers the member segment and its `source_span` runs
from the receiver start to the member end. An unparenthesized `name.Member` or
`a.b.Member` is one qualified-name token, so it admits no whitespace or comment
around its dots; the binder splits it. After a postfix receiver the parser splits
a member token such as `.Target.Virtue` into chained properties. A member
statement cannot take a block; a property used as a statement (`coach.CancelAction;`)
is a syntax error with code `MEMBER_KIND`. A trailing dot or a literal receiver is
a syntax error. The binder rules are in the [language reference](language.md#receiver-calls).

```text
Notification(ThisCard.FullName + " has been added to class");

if ((ThisCard.Dislike(Context.NpcTalkTarget) > 29) ||
    (ThisCard.Hate(Context.NpcTalkTarget) > 29)) {
  love = TriggeringCard.Love(Context.NpcTalkTarget);
}
```

Literals become typed constant expressions. Action defaults are applied during
binding. `Notification(message)` therefore writes the same serialized action
as `Notification(message, false)`.

`SIGNED_INT` tokens include their sign, so `-2147483648` is one literal. Binding
rejects int literals outside the int32 range with `INT_OUT_OF_RANGE`, at the
literal, including `const` values and raw `constant` payloads.

Ordinary decimal float literals are used for finite values that do not require
wire-level recovery. Binding rejects decimal overflow, including exponents that
convert to infinity, with `FLOAT_OUT_OF_RANGE`. The serializer stores raw
IEEE-754 binary32 bytes. To preserve signed zero, subnormals, infinities, or NaN
payload bits exactly, use:

```text
float_bits(0x80000000) // negative zero
float_bits(0x7f800000) // positive infinity
float_bits(0x7fa00001) // NaN with a preserved payload
```

The formatter emits `float_bits(...)` automatically whenever a decoded float
cannot be represented safely by an ordinary decimal literal. Finite ordinary
floats continue to use decimal syntax.

## Raw Forms

Raw forms expose the AA2 Serialized IR when metadata names are unknown,
ambiguous, or insufficient for exact recovery:

```text
raw_event 9001;
raw_action 9002(raw_expression type 77 9004 { parameters [ ]; }) {
  raw_action 9003;
}
```

```text
raw_expression int 1 {
  constant "text";
}
raw_expression int 2 {
  variable "serialized name";
}
raw_expression int 3 {
  named_constant int 7;
}
raw_expression type 77 9004 {
  parameters [ ];
}
```

The expression payload branch is selected by the numeric ID:

- ID `1` requires a constant payload.
- ID `2` requires a variable-name payload.
- ID `3` requires a type-scoped named-constant payload.
- Other IDs require a parameter list.

Raw forms preserve numeric action/event IDs, expression type scopes, named
constant scopes, unknown references, nested action children, and serialized
global state when the grammar has a matching production. Raw forms do not apply
metadata defaults. Ordinary source and model validation/compilation strictly
check registry identities, signatures, types, variable scopes and assignment/loop
targets, including raw descendants and unused definitions. Known valid raw
records compile; unknown or invalid records survive only binary recovery
(decode, then encode). Structural writer constraints remain in force. The formatter reports a `FormatError` for
global or local declarations whose type is invalid, unknown, or disagrees with
their values/default expression, because declarations have no raw recovery
bypass for those cases.

## Recovery Limits

`decode_module` reads one module and reports any trailing bytes separately from
the returned module. The module model does not retain those bytes, so formatting
and re-encoding the module cannot reproduce a trailer. Boolean fields are
decoded as false for byte `0` and true for every nonzero byte; the writer emits
canonical `0` or `1`, so a noncanonical boolean byte is also normalized.

`encode_module` writes models accepted by the model and structural writer, but
does not run full semantic validation. It can therefore encode some
semantically invalid records. `validate_module` and `compile_module` apply
strict semantic validation by default, including to raw-marked nodes. Their
explicit native profile checks the pinned projection before reference resolution,
without relaxing checks based on raw provenance; see the
[profile contract](language.md#validation-profiles).
Raw markers select representation, never a permissive validation policy.
`validate_source`, `parse_and_validate_source` and `compile_source` use strict
semantic validation and cannot bypass it through raw syntax. Global and local declaration type mismatches
and invalid/unknown declaration types have no raw declaration recovery and
cause formatting to fail explicitly. Numeric type IDs remain available in raw
expression forms.

`decompile_module` returns a `DecompileResult` with source, decode details and
diagnostics. Formatting decisions emit located `RAW_FALLBACK` warnings, and
strict validation of the original SIR emits separate semantic errors under the
selected context. Recovery success does not imply compilation success.

## Source Spans and Lowering

Parsed declarations, statements, and expressions carry one-based inclusive
source spans. Raw payload wrappers use their enclosing expression's location.
Spans are diagnostic data and are not serialized.

AST declarations and named uses additionally retain optional token spans:
`name_span`, assignment/loop `target_span`, import `path_span`, and
trigger-import `template_span`. Quoted names include their delimiters and
authored escapes; qualified names cover the complete name token. These
annotations use the same inclusive Unicode code-point columns, do not affect
equality, and leave enclosing node spans unchanged. Shared `Diagnostic` values
and `SourceParseError` optionally retain their full `source_span` without
changing equality or printed locations. Unexpected end-of-input spans point to
the insertion position after the last character.

`BoundModule.references` retains exact authored use spans and binder-selected
declarations/metadata for editor navigation. These annotations do not participate
in HIR equality, resource node counts, or serialized output. Macro/template
expansion retains authored definition targets and introduces no generated-name
declarations. Overload trials commit navigation records only after selection.

`SourceIf` and `BoundIf` hold typed `else_if` records and an optional
`else_branch`. `None` means absent; a `SourceElse`/`BoundElse` with an empty
body means present. `SourceElseIf`/`BoundElseIf` and `SourceElse`/`BoundElse`
also serve as standalone statements. Each branch retains its own clause span
through binding and lowering to its GUI action and action call.

`parse_source_unit` retains the module and definitions. `parse_source_ast`
remains the module-only syntax API and reports `MACRO_UNIT_REQUIRED` for
macro-bearing source instead of discarding definitions. Both check syntax,
string/number conversion, and raw payload
branches, raising `SourceParseError`. It leaves decimal float range and name/type
resolution to binding, which raises `SourceBindingError`. Module declaration and dependency rules
belong to semantic validation, so parsing alone does not establish validity.

Source processing also applies explicit `SourceLimits` before recursive work.
The defaults allow 4,194,304 Unicode characters, 200,000 nodes per stage,
syntax depth 256, and combined statement/expression nesting 64. Positioned tree
inspection and AST transformation are iterative; delimiters inside strings or
comments do not contribute syntax depth. Direct AST/HIR binding/lowering use
the same node/depth budgets. These operational bounds do not change grammar
version; see [source resource limits](language.md#source-resource-limits)
for counting rules, supported option ceilings, and CLI flags.

`validate_source` and `parse_and_validate_source` return structured diagnostics
for syntax, binding, budget, and semantic input failures. Parsing/binding stops at the
first failure; semantic validation can report multiple errors. Dependencies
and global declarations are checked once per module, before trigger checks.
`compile_source` also checks writer constraints and raises `CompileError` on
input failure. `compile_module` does the same under strict model semantics.
Validation alone does not check every writer width or resource limit.

Invalid JSON escapes use `INVALID_STRING`; numeric conversion failures use
`INVALID_NUMBER`; incorrect raw payload branches use `PAYLOAD_MISMATCH`.
Known names/calls with the wrong result type use `SOURCE_TYPE_MISMATCH`, while
incorrect call argument counts use `EXPRESSION_ARITY`. Nested argument failures
retain the offending expression's code and source span. When several overloads
fail, binding reports the failure from the candidate that accepted the most
preceding arguments, breaking ties in catalog candidate order.

Semantic diagnostics use source spans when present. Otherwise decoded nodes
retain their absolute binary paths and byte offsets; a field suffix is appended
once. Unlocated models use logical traversal paths. Writer errors retain their
structural paths and offsets as `WRITE_ERROR`. Registry and policy failures
propagate as `MetadataError`, separately from source diagnostics. Unexpected
programming exceptions are not converted to input failures.

The compiler pipeline is:

```text
source text
    -> Source AST
    -> Bound HIR
    -> AA2 Serialized IR
    -> validation
    -> binary writer
```

The reverse invariant for supported modules is:

```text
binary -> SIR -> unified source -> SIR -> identical binary
```

The serialized IR retains module order, vector order, raw IDs, type scopes,
UTF-16 strings, global runtime state, expression payload branches, and nested
GUI actions.
