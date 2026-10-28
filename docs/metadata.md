# Metadata catalogs

The project keeps source-derived facts apart from source-language choices:

```text
aa2modulus/metadata/registry/      generated AAUnlimited registry data
aa2modulus/language/policy.toml    editable .aa2m language policy
```

Registry data describes native actions, events, expressions and named
constants. The policy selects their source spellings, operators, visibility,
short-circuit behavior and trailing action defaults. Both are loaded into
immutable indexes and carried together by `SourceContext`.

Its `catalog` composes native row and wire identities, signatures, candidate
source forms and policy event values once per resolved metadata and policy
pair. Binding, formatting, completion and signature help query the same catalog
for candidate identities, canonical forms and literal source values. Operator
syntax and trailing defaults remain explicit policy choices.

## Generated registry facts

Regenerate the five registry JSON files (actions, events, expressions,
named_constants and manifest) from the clean, pinned, read-only source checkout
with `mise run registry --source-root <dir>`. This is infrequent manual
maintenance. Ordinary checks neither require the checkout nor regenerate its
data.

The manifest and the four native tables use schema revision 3 and generator
version 4. Each native row keeps its original fields and adds registration
provenance. Actions and expressions also include implementation symbols.
Constants include a separate `resolved_value`, taken from native literals or
from the generator's checked enum declarations. Their original `value` and
`value_expression` remain intact.

The manifest records the hash of every source file the generator read. Some
facts need judgment, such as which events a callback reads data in. The
generator does not produce them. They are authored in the policy
([event values](#event-values)).

Runtime loading validates files, fields, IDs, signatures, values and counts
before building indexes. Inconsistent manifests, unknown fields, duplicate keys
and malformed values fail with contextual errors. The loader reads package
resources only and never needs the checkout. Snapshots own read-only copies of
the source-hash mappings that callers supply.

The pinned source has two generator quirks:

- `Expressions.cpp` contains Windows-1252 text, so source files are decoded as
  UTF-8 with a CP1252 fallback.
- Four LUA expression rows (int 152, bool 52, float 15, string 25) use
  `ACTIONCAT_GENERAL`. The parser accepts it as an exact alias of
  `EXPRCAT_GENERAL`.

Both are handled in `tools/registry/`.

Expression identities are scoped by return type and ID. Named constants keep
list order and duplicate IDs. Lookup checks explicit IDs first, then the 1-based
position. Policy names select the native first-ID winner and collapse
equivalent rows. A shadowed row name cannot claim a different value under that
ID. A positional-only serialized reference stays unannotated, so raw formatting
preserves its numeric value. Native lookup rules, duplicate-ID outcomes and
pinned source pointers are in
[native format](native-format.md#lookups-and-identity).

`context.catalog.native_targets` uses `WireIdentity`. `constant_rows` keeps the
scoped `RowIdentity` ordinals. It also records first-ID lookup, shadowed
values, equivalent duplicates and positional selection separately. The native
save identity and the row seen after reload stay distinct. For int:100, the
lookup scope is INT, the native declaration and save scope is BOOL, and
BOOL/100 has no reload row. Its callback returns INT under NPC_RESPONSE and
BOOL elsewhere (policy `[event_values]`).

`catalog.candidates(...)` exposes exact candidates without ranking or casts.
Candidate membership alone does not prove native initialization or
callback-context safety. Canonical forms describe usable spellings in matching
type and argument contexts. Binding and formatting also check the actual scope
and unique selection.

Validation reads the same reviewed targets. Known event-dependent Value
mismatches are strict errors and native-profile warnings. A missing event
context stays unknown. INT/100's native declaration incompatibility and its
re-save hazard have separate diagnostics.

Model-only validation (`validate_module` without a catalog, and
`compile_module`) builds a cached catalog from the shipped policy. A policy
that does not fit the metadata raises `MetadataError`. There is no fallback to
an empty policy. Source and decompiler operations reuse `context.catalog`.

INT/100 is a known AAUnlimited defect. Fixing it belongs upstream: declare the
getter as INT, define a consistent wrong-context result or an explicit failure,
then verify native initialization, evaluation and re-save. This toolchain
diagnoses the defect and preserves the pinned source. It does not repair
modules, and it does not claim that native execution was tested.

Do not edit generated registry files to add names or language defaults. Put
those choices in `aa2modulus/language/policy.toml`.

## Editable language policy

The policy is a commented TOML file maintained by project maintainers. It holds
only authored choices:

- operator token mappings
- trailing action defaults
- preferred names
- readable expressions
- literal source values
- receiver member forms
- protected names

Everything the registry or the grammar already determines is derived when the
policy loads: operator precedence, fixity, associativity and short-circuiting,
operator and member signatures, member slot numbers, and literal row positions.
Comments document why a choice exists.

Every entry is checked against the loaded registry. A registry change that
breaks a choice fails with a message naming the fact that changed. Examples are
a literal whose row value moved, a preferred name that now collides with a
native name, and a readable marker whose native declaration was fixed. There
are no hash guards to refresh.

Target notation is the same everywhere. Actions and events use their numeric ID
(`108`). Expressions and named constants use `"type:id"` (`"int:24"`), with
type `invalid`, `int`, `bool`, `float` or `string`. Names must be source names
(see below).

Only `language_version` is required. Omitted sections are empty. Unknown keys,
duplicate keys (rejected by TOML itself), non-finite floats, dates and integers
outside signed 32-bit fail with contextual `MetadataError` messages that name
the TOML key path. The CLI reports configuration failures separately from input
errors. `language_version` is the source language version and lives only in
this file. Version numbers quoted elsewhere in the docs are historical.

### Fixed operator syntax

The package grammar owns the operator table:

| Tokens | Precedence | Fixity | Associativity | Short circuit |
| --- | ---: | --- | --- | --- |
| `||` | 10 | infix | left | true |
| `&&` | 20 | infix | left | true |
| `==`, `!=` | 30 | infix | left | false |
| `<`, `<=`, `>`, `>=` | 40 | infix | left | false |
| `+`, `-` | 50 | infix | left | false |
| `*`, `/` | 60 | infix | left | false |
| `!` | 70 | prefix | right | false |

Each equality or relational tier permits one comparison. Parentheses express
nested comparisons, and the formatter preserves them. The policy only maps each
token to native expressions. The table supplies the rest. Native BOOL
expressions 4 and 5 implement short circuiting, not compiler-generated
branches.

Branch keywords map to the fixed action IDs 2, 3 and 4 (`if`, `elseif`,
`else`). Formatting uses branch syntax only for visible records with the fixed
signature. Otherwise it preserves raw actions.

### Protected names

`protected_names` is a root list of unqualified names that source can never
redeclare or shadow. The shipped policy lists `ThisCard` and `TriggeringCard`.
Each entry must be the unqualified preferred name of exactly one zero-argument
expression. Matching is case-insensitive.

Bare declarations of a protected name fail with `PROTECTED_NAME`. Serialized
variables with such names use quoted declarations and `variable("...")`
references (see [protected names](language-contract.md#protected-names)).

### Acknowledgeable codes

`acknowledgeable` is a root list of validator codes that a source
[`@allow(CODE)`](language-contract.md#acknowledging-native-hazards) may
acknowledge. The shipped policy lists `REVIEWED_VALUE_TYPE_MISMATCH`,
`NATIVE_DEFECTIVE_EXPRESSION` and `EXPRESSION_METADATA_RETURN_TYPE_MISMATCH`.
Each entry must appear once and must be one of the native hazard codes the
validator reports (`NATIVE_HAZARD_CODES` in `aa2modulus/core/diagnostics.py`).
Authoring checks such as type, scope or dependency findings cannot be listed.
An empty list makes every `@allow` an `ALLOW_NOT_PERMITTED` error.

### Preferred names and lookup

`preferred_names` assigns the one spelling of an action, expression or named
constant. Events keep their native symbols. For example:

```toml
[preferred_names.actions]
110 = "ClassStorage.SetInt"             # Set Class Storage Integer

[preferred_names.expressions]
"int:121" = "ClassStorage.GetInt"       # Get Class Storage Int
```

Names must be ASCII identifiers or contiguous dot-separated identifiers, with
no keyword segment. Dots are never flattened: `ClassStorage.GetInt` does not
create `ClassStorageGetInt`. The first segment of a qualified name (the
namespace root) must start with an uppercase ASCII letter. Roots are unique
ignoring case, and they match case-sensitively in source. Later segments and
unqualified names match case-insensitively. Output keeps the configured
spelling.

A target with a canonical spelling accepts only that spelling. The canonical
spelling is a preferred name, the native symbol for an event, or the
[member form](#receiver-member-forms) for a card-first target. Native record
names, normalized identifiers and interactive labels are not accepted for it
(`AddLikePoints`, `NpcTalkTarget`, `CardAddedToClass`, the constant label
`LOVE`).

A member-canonical target accepts no flat spelling at all. Native fallbacks and
the former qualified names (`Character.SetVirtue`) are unknown names. The error
hints at the member form: `use 'coach.SetVirtue(3)'` for
`Character.SetVirtue(coach, 3)`, or `use '<card>.Virtue'` when there are no
usable arguments. The catalog exposes the member as the target's single
canonical `SourceForm` (`kind == "member"`, and `form.member` is the
`MemberForm`). `catalog.canonical_name` returns the member name, and
`catalog.member_form(kind, identifier, scope)` returns the receiver projection.

A target with no canonical spelling keeps its native record names, so recovery
is unaffected. Examples are grammar-owned branch and loop actions such as
`ElseValue`, payload markers and int:99.

The catalog records each retired spelling. An unknown action, expression,
event, constant or member name that equals one adds `; use '<canonical>'` to
the error. When several targets share the name, the error lists all canonical
names.

GUI templates and prose are kept as provenance and never normalized into
names. For example, `%p.SetStamina = %p` does not introduce `PSetStaminaP`, and
`Notification(text: %p, isImportant: %p)` does not introduce
`NotificationTextPIsImportantP`. Use `coach.SetStamina` and `Notification`.

A preferred name that is the native name of a different target is a policy
error. Validation checks raw native names, even when that target no longer
accepts them. Duplicate canonical signatures are rejected.

Unqualified expressions try variables first, then zero-argument expressions,
then named constants. Qualified built-ins bypass variable lookup, including
quoted variables that contain dots.

The formatter uses a preferred name, or a deterministic registry fallback for a
target without a canonical spelling, only when that spelling resolves to the
same identity. Operators and control flow take precedence. Raw provenance,
unknown IDs, incompatible signatures and unresolved collisions stay raw.
Named-constant targets require explicit IDs and select their actual first
native row, merging equivalent duplicates. Conflicting row labels produce
targeted diagnostics. Positional-only entries remain available through raw
forms and registry lookup.

### Naming convention

Every canonical name follows one convention, so a name shows its domain and
role. Source names are PascalCase ASCII identifiers. Acronyms count as words
(`Npc`, `Pc`, `Lua`, `Csv`).

- Shape. A target whose native slot 0 is a card is a member of that card and has
  no preferred name: `coach.SetVirtue(3)`, `coach.Virtue`. This covers 213
  actions and expressions: stats, personality, traits, relationship points,
  opinions, H stats, items, names, appearance, mood, style, preferences,
  modifiers, partners, grades, lovers, card storage, and NPC commands on a card.
  Every other action and expression is `Root.Name`. Named constants and
  literals are `Constants.Category.UPPER_SNAKE`. There is no `Character` root.
- Roots (case-sensitive):
  - `Npc`: card-less NPC commands and checks (action-kind predicates, poses).
  - `Context`: values and settable response state of the current event.
  - `Conversation`: PC conversation state, lines, actors and responses.
  - `H`: H-scene state and control.
  - `Globals`: game-wide and class-wide state (days, periods, player character,
    timers, seats, clubs, class membership).
  - `ClassStorage`, `Lua`, `Math` (random, roll) and `Text` (string functions).
  - `Constants`: named constants.
- Core names are unqualified: `ThisCard`, `TriggeringCard`, `Notification`,
  `WriteLog`, `StopThread`, `StopThreadIf`, `JumpIf`, and the conversions
  `ToInt`, `ToFloat` and `ToString`.
- Verbs. A getter is a noun (`coach.Virtue`). Its setter is `Set` plus the same
  noun (`coach.SetVirtue`). Increments are `Add...` and removals are
  `Remove...`. Boolean getters for possession, relation or property read as
  predicates (`Has...`, `Is...`): `coach.HasGlasses` pairs with
  `coach.SetGlasses`. Setting-like flags keep the noun (`Globals.AutoPc`).
  Response percentages end in `Chance`. One-argument totals start with `Total`.
- Overloads differ only by parameter types with the same meaning (`ToInt` for
  float and string). Never overload by result type alone: `Lua.CallInt`,
  `Lua.CallBool`, `Lua.CallFloat` and `Lua.CallString` stay distinct. Actions
  cannot overload.
- Members. The member name is the canonical spelling of a card-first target.
  The receiver is the card in slot 0: `actor.AddLike(target, 30)`. Argument
  names are camelCase forms of the native template labels.
- Constants. Categories are singular PascalCase (`Relationship`, `Conversation`,
  `Trait`, `Day`, `Period`, `PregnancyRisk`, `EventType`, `Mood`, `Preference`,
  `Opinion`, `Room`). The last segment is `UPPER_SNAKE`:
  `Constants.Mood.JEALOUS`, `Constants.Room.SCHOOL_GATES`.
- Events keep their native symbols (`on CARD_ADDED;`). Event-type constants use
  the native category name `EventType` (`Constants.EventType.KEY_PRESS`).
- Native spellings (`AddLikePoints`, `NpcTalkTarget`) are not accepted for a
  target with a preferred name or member form.

### Readable expressions

Some native declarations disagree with the wire scope used to call them. The
formatter normally keeps such expressions raw. `[readable]` opts a target into
output under its preferred name:

```toml
[preferred_names.expressions]
"int:100" = "Context.NpcOriginalResponse"

[readable]
# INT/100 is declared BOOL natively; readable INT/100 output is allowed and the
# event-dependent value and BOOL/100 re-save defect remain separate diagnostics.
expressions = ["int:100"]
```

A readable target needs a preferred name. The marker permits readable output.
It does not change the BOOL native declaration and does not suppress native
validation errors. If the native declaration is corrected, loading fails until
the marker is removed, so stale exceptions cannot linger.

### Native defects

`[defects]` records native targets that cannot work in AAUnlimited as pinned.
Every use reports `NATIVE_DEFECTIVE_EXPRESSION` with the recorded reason. It is
an error under strict validation and a warning under `profile="native"`. The
target still parses, decodes, formats and keeps its name, so existing binaries
stay recoverable:

```toml
[defects.expressions]
"string:13" = { declared = ["int", "int", "int", "string"], reason = "its first parameter is declared int, but ..." }
```

`declared` must equal the registry's parameter types. A regenerated registry
with a corrected declaration fails to load until the entry is reviewed and
removed. The fix belongs upstream, and the toolchain never repairs these
targets. Every validation path reports defects, including
`validate_module(module)` without a `catalog` and `compile_module`, which load
the shipped policy. Evidence for STRING/13 (`Text.Replace`) is
[N12](native-format.md#native-source-evidence).

### Event values

`[event_values.expressions]` lists expressions whose native callback reads
event data, so the value exists only during some events. Each type key (`int`,
`bool`, `float`, `string`) lists the event IDs in which the callback returns
event data of that type. In every other event it returns `otherwise`, whose
TOML type selects the wire type:

```toml
[event_values.expressions]
"int:100" = { callback = "Thread::GetNpcResponseOriginalAnswer", int = [8], otherwise = false }
```

Validation reports a use whose type differs from the event's type
(`REVIEWED_VALUE_TYPE_MISMATCH`). It also reports a trigger without a fully
known event (`REVIEWED_VALUE_CONTEXT_UNKNOWN`). See the
[language reference](language-contract.md).

`callback` must equal the registry's implementation symbol, so a regenerated
registry that changes it fails to load until the entry is reviewed. Every
listed event must exist, and no event may appear under two types. Evidence:
[N6, N7 and N11](native-format.md#native-source-evidence).

### Result roles

`[result_roles.expressions]` says what an expression's value means. It uses the
same role words as member receivers and arguments:

```toml
[result_roles.expressions]
"int:11" = "card"   # GetNpcResponseTarget: answeredTowards (a seat), else -1
"int:103" = "card"  # GetTarget: also the member property coach.Target
```

A role must be one that some member receiver or argument already uses with the
expression's result type (`card` is an `int` role). Unknown targets and payload
markers are rejected. The key is the native expression, so the role applies to
every spelling, including member properties.

Role `card` types the result as the source type
[`card`](language-contract.md#cards). It is accepted where a card is expected,
while an untagged `int` there needs `Card(...)`. The wire type stays `int`.
Hover shows `Returns: card` and signatures show `-> card`. Completion ranks card
values first where a card is expected. Other roles are documentation only.

The default policy tags 16 seat-valued expressions, each with its pinned-source
evidence in a comment. `Context.NpcTalkTarget`, `Context.NpcTalkAbout` and
`Context.RelationshipTowards` return 0, a valid seat, outside their events.
Context checks report those reads, so they are cards too (owner, 2026-10-17).

### Parameter names

`[parameter_names.actions]` and `[parameter_names.expressions]` name every
native parameter slot of a target that is not a member:

```toml
[parameter_names.actions]
51 = ["pc", "partner"]                 # H.Start

[parameter_names.expressions]
"int:121" = ["key", "fallback"]        # ClassStorage.GetInt
```

The list length must equal the native parameter count. Names are distinct,
unqualified, non-keyword identifiers. Member targets are rejected here because
their `[members]` arguments already name them. Native `interactive_name` labels
are GUI text and are not parsed (several use reserved words such as `default`,
`from` and `to`).

Names are editor data only. Hover, signature help and the built-in pages (in
the editor and on the website) show them. Binding and output are unchanged. The default policy
names all 104 non-member parameterized targets that have a source spelling.
Actions 1 and 9 are structural and have none.

### Parameter roles

`[parameter_roles.actions]` and `[parameter_roles.expressions]` give roles to
named slots of non-member targets, keyed by their `[parameter_names]`:

```toml
[parameter_roles.actions]
51 = { pc = "card", partner = "card" }      # H.Start: Thread::StartHScene

[parameter_roles.expressions]
"bool:16" = { seat = "card" }               # Globals.IsSeatFilled
```

Each name must be one of the target's `[parameter_names]`. The role must be one
that some member receiver or argument already uses with the slot's type. Role
`card` types the slot as a source `card`, so an `int` argument other than a
literal or constant needs `Card(...)`.

The default policy tags the seat slots of actions 51, 91, 119 and 120 and
`bool:16`. Each reads the slot as a seat and checks it with
`ActionSeatInvalid` or `ExpressionSeatInvalid` in the pinned `Actions.cpp` or
`Expressions.cpp`. Actions 119 and 120 pass that seat to `GameState::kickCard`
and `addCard`. Signature help and the generated documentation show
`seat: card`.

### Descriptions

`[descriptions.expressions]` replaces a native expression description wherever
it is shown: hover, completion, signature help and the built-in pages (in the
editor and on the website). Keys use the `"type:id"` target notation. Text is trimmed and
must not be empty:

```toml
[descriptions.expressions]
"string:13" = "Does not work in AAUnlimited: ..."
```

The shipped tables override only `Text.Replace` (STRING/13), whose description
warns that it does not work ([native defects](#native-defects)). Every other
target uses its native description.

### Receiver member forms

`[members]` entries configure the canonical spelling of one card-first native
action or expression: `receiver.Member(arguments)`, or the property
`receiver.Member` when an expression has no explicit arguments. Keys use target
notation. Each value is a signature string of the member name and its
`name: role` arguments:

```toml
[members.actions]
13 = "AddLike(towards: card, amount: points)"   # Add Like Points
88 = "CancelAction"                             # no arguments

[members.expressions]
"int:25" = "Virtue"                             # coach.Virtue
```

The member name and argument names are unqualified, non-keyword identifiers.
`Name()` equals `Name`. The receiver is always a `card` and fills native slot
0. The arguments fill slots 1..n in order, so the argument count must be one
less than the native parameter count. The signature and result type come from
the native target.

The initial contract accepts only a slot-0 `int` receiver and targets without
structured (`invalid`) parameters or payload markers. It allows at most one form
per spelling, target kind and argument count, so one name may have both an
action form and an expression form. Trailing defaults, permuted slots and
dropped or duplicated receivers cannot be expressed. Role `card` types the
receiver or an argument as the source type
[`card`](language-contract.md#cards) (still an `int` on the wire). Other roles
are documentation and completion data.

The default policy configures 213 members (98 actions, 115 expressions), one
for every card-first action and expression. A member target has no preferred
name (policy validation rejects both on one target). The member is therefore
its only source spelling, and the formatter and decompiler write it.

A bare built-in is also a receiver when it is a registered zero-argument `int`
expression (`ThisCard.Virtue`, `TriggeringCard.AddLike(...)`). Static namespace
roots (the first segments of every configured qualified name, matched
case-sensitively) remain the binder's first interpretation of a dotted token.
See [Receiver Calls](language-contract.md#receiver-calls).

### Literal source values

`[literals]` gives qualified names to values of named-constant rows that their
own ID cannot select, because an earlier row shares the ID:

```toml
[literals]
"Constants.Room.SCHOOL_GATES" = { row = "School gates", value = 0 }
"Constants.Period.EXAM"       = { row = "EXAM", value = 11 }
```

`row` is the native row name. Add `category = "..."` when the name occurs more
than once in the scope. The TOML type of `value` selects the scope (`0` is
int, `0.0` float, `false` bool, `"x"` string). The value must equal the row's
verified value, and the row must still be shadowed. If its own ID ever selects
it, use the native constant instead. A literal name cannot collide with a
native getter or named constant.

Twelve defaults cover the shadowed room rows and `Constants.Period.EXAM`.
`Constants.Room.SCHOOL_GATES` lowers to INT/0. Literals lower through
BoundLiteral, while native references retain their wire IDs. Literal recovery
remains numeric.

### Defining an action default

Defaults fill trailing serialized action parameters. The table key is the
action ID, each entry key is a parameter index, and the TOML value type selects
the wire type:

```toml
[action_defaults.108]  # Notification
1 = false
```

This lets `Notification("Loaded")` lower to `Notification("Loaded", false)`.
Binding inserts the value before lowering. The loader rejects unknown actions,
out-of-range or non-trailing parameters, and values of the wrong type.

Use only defaults that native behavior supports. The selected default is
`false` for the `isImportant` parameter of `Notification`. Other actions
require their full declared arguments. A zero or false value may change state,
and runtime behavior such as an optional emitted event does not make a source
argument optional. Expressions have no source-level optional parameters.
Storage getter fallback values remain explicit.

## Float wire policy

The serializer stores raw IEEE-754 binary32 values. Preserve signed zero,
subnormals, infinities and NaN payload bits. Use `float_bits(0xHHHHHHHH)` when
exact bits matter. Formatting emits it for unusual decoded values. The logical
IR retains unusual bits as a model annotation. Ordinary finite values keep the
`{type, value}` shape.

### Adding an operator

`[operators]` maps each grammar token to the native expressions it may lower
to, one per signature:

```toml
[operators]
"+" = ["int:5", "float:5", "string:8"]   # string + string concatenates
```

The loader takes each expression's signature from the registry and its syntax
from the fixed table above. Prefix tokens need one-parameter expressions, and
infix tokens need two. A token may not map two expressions with the same
signature, and serialized payload-marker IDs cannot be operator targets.
Tokens outside the grammar are rejected.

## Validation workflow

### Built-ins pages

`mise run docs:builtins` writes the website's
[built-ins pages](reference/builtins/index.md) from the editor catalog. It
writes one page per entry kind and native category, at the path each entry's
`docPath` names. It also writes an overview and the section's `SUMMARY.md`
navigation (literate-nav). Entries have the same text as the editor's built-in
pages, under a heading whose anchor is the entry's ID.

Add `--check` to compare instead of writing. Regenerate the pages after a
registry or policy change. They are outside pytest and `mise run verify`.

`aa2modulus editor-data catalog [--output <path>]` prints the built-ins catalog
(schema `aa2modulus.editor-builtins.v1`) from the same catalog. The server's
`aa2m-builtin:` pages and the website's pages render these entries. It
contains:

- canonical names
- signatures with parameter names and roles
- descriptions (overrides first)
- value events from policy `[event_values]`
- one placeholder example per entry

Every example is compiled in a trigger for one of its value events. The export
reports three things on stderr:

- Omitted examples. Currently there are two. INT/100 fails with
  `EXPRESSION_METADATA_RETURN_TYPE_MISMATCH` because its native declaration is
  BOOL. STRING/13 (`Text.Replace`) fails with `NATIVE_DEFECTIVE_EXPRESSION`.
- Targets skipped for lack of a source spelling.
- Parameterized targets without names.

Never edit catalog output or the generated pages by hand. Better
documentation comes from better policy data.

After editing the policy, run `mise run test -m metadata`. Use
`mise run verify` for the full suite. Metadata tests exercise shipped spellings
through compilation, policy effects and representative resource-loading
failures. Programmatic policy objects and custom registries are internal
maintenance facilities, not a supported Python embedding API. Runtime commands
use package-local catalogs without a source checkout. Regeneration remains a
manual `mise run registry --source-root <dir>` operation.
