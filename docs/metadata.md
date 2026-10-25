# Metadata Catalogs

The project separates source-derived facts from source-language choices:

```text
aa2modulus/metadata/registry/      generated AAUnlimited registry data
aa2modulus/language/policy.toml    editable .aa2m language policy
```

Registry data describes native actions, events, expressions, and named
constants. The policy selects their source spellings, operators, visibility,
short-circuit behavior, and trailing action defaults. Both are loaded into
immutable indexes and carried together by `SourceContext`.
Its `catalog` composes native row/wire identities, signatures, candidate source
forms and policy event values once per resolved metadata/policy pair.
Binding, formatting, completion and signature help query the same catalog for
candidate identities, canonical forms and literal source values. Operator syntax
and trailing defaults remain explicit policy choices.

## Generated Registry Facts

Regenerate the six registry JSON files from the clean, pinned, read-only
source checkout with `mise run registry --source-root <dir>`. This is infrequent manual maintenance;
ordinary checks neither require the checkout nor regenerate its data.

The manifest and four native tables use schema revision 3 and generator version
4. Each native row retains its original fields and adds registration provenance;
actions/expressions include implementation symbols. Constants include a separate
`resolved_value`, obtained from native literals or the generator's checked enum
declarations. Their original `value`/`value_expression` remain intact.

The manifest records the hash of every source file the generator read.
Facts that need judgment, such as which events a callback reads data in, are
not generated; they are authored in the policy ([event values](#event-values)).

Runtime loading validates files, fields, IDs, signatures, values and counts
before building indexes. Inconsistent manifests, unknown fields, duplicate keys
and malformed values fail with contextual errors. The loader reads package
resources only; it never needs the checkout. Snapshots own read-only copies of
source-hash mappings supplied by callers.

Generator quirks in the pinned source: `Expressions.cpp` contains Windows-1252
text, so source files are decoded as UTF-8 with a CP1252 fallback; four LUA
expression rows (int 152, bool 52, float 15, string 25) use `ACTIONCAT_GENERAL`,
which the parser accepts as an exact alias of `EXPRCAT_GENERAL`. Both are in
`tools/registry/`.

Expression identities are scoped by return type and ID. Named constants retain
list order and duplicate IDs; lookup checks explicit IDs, then the 1-based
position. Policy names select the native first-ID winner and collapse equivalent
rows; shadowed row names cannot claim a different value under that ID.
A positional-only serialized reference stays unannotated
so raw formatting preserves its numeric value.
Native lookup rules, duplicate-ID outcomes and pinned source pointers are in
[native format](native-format.md#lookups-and-identity).

`context.catalog.native_targets` uses `WireIdentity`; `constant_rows` preserves
scoped `RowIdentity` ordinals and separately records first-ID lookup, shadowed
values, equivalent duplicates and positional selection. Native save identity
and subsequent reload row remain distinct. For int:100, lookup scope is INT,
the native declaration/save scope is BOOL, and BOOL/100 has no reload row.
Its callback returns INT under NPC_RESPONSE and BOOL elsewhere (policy `[event_values]`).

`catalog.candidates(...)` exposes exact candidates without ranking or casts.
Candidate membership alone does not prove native initialization or callback-context
safety. Canonical forms describe usable spellings in matching type/argument
contexts; binding and formatting also check actual scope and unique selection.

Validation reads the same reviewed targets. Known event-dependent Value mismatches
are strict errors and native-profile warnings; missing event context stays unknown.
INT/100's native declaration incompatibility and re-save hazard have separate
diagnostics. Model-only validation (`validate_module` without a catalog,
`compile_module`) composes a cached catalog with the shipped policy, falling
back to an empty policy for metadata that policy does not fit; source/decompiler
operations reuse `context.catalog`.

INT/100 is a known AAUnlimited defect. Fixing it belongs upstream: declare the
getter as INT, define a consistent wrong-context result or explicit failure, then
verify native initialization, evaluation and re-save. This toolchain diagnoses
the defect, preserves the pinned source, does not repair modules, and does not
claim native execution was tested.

Do not edit generated registry files to add names or language defaults. Put
those choices in
`aa2modulus/language/policy.toml`.

## Editable Language Policy

The policy is a commented TOML file maintained by project maintainers. It holds only
authored choices: operator token mappings, trailing action defaults, preferred
names, readable expressions, literal source values, receiver member forms and
protected names. Everything the registry or the grammar
already determines is derived when the policy loads: operator precedence, fixity,
associativity and short-circuiting; operator and member signatures; member slot
numbers; and literal row positions. Comments document why a choice exists.

Every entry is checked against the loaded registry. A registry change that
breaks a choice fails with a message naming the fact that changed, for example
a literal whose row value moved, a preferred name that now collides with a native name, or
a readable marker whose native declaration was fixed. There are no hash guards
to refresh.

Target notation is the same everywhere: actions and events use their numeric ID
(`108`); expressions and named constants use `"type:id"` (`"int:24"`), with type
`invalid`, `int`, `bool`, `float` or `string`. Names must be source names (see
below). Only `language_version` is required; omitted sections are
empty. Unknown keys, duplicate keys (rejected by TOML itself), non-finite floats,
dates and integers outside signed 32-bit fail with contextual `MetadataError`
messages that name the TOML key path; the CLI reports configuration failures
separately from input errors. `language_version` is the source language version
and lives only in this file; version numbers quoted elsewhere in the docs are
historical.

### Fixed Operator Syntax

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

Each equality or relational tier permits one comparison; parentheses express
nested comparisons and the formatter preserves them. The policy only maps each
token to native expressions; the table supplies the rest. Short circuiting is
implemented by native BOOL expressions 4 and 5, not compiler-generated branches.

Branch keywords map to fixed action IDs 2/3/4 (`if`/`elseif`/`else`). Formatting
uses branch syntax only for visible records with the fixed signature; otherwise
it preserves raw actions.

### Protected Names

`protected_names` is a root list of unqualified names that source can never
redeclare or shadow; the shipped policy lists `ThisCard` and `TriggeringCard`.
Each entry must be the unqualified preferred name of exactly one zero-argument
expression. Matching is case-insensitive. Bare
declarations of a protected name fail with `PROTECTED_NAME`; serialized
variables with such names use quoted declarations and `variable("...")`
references (see [protected names](language.md#protected-names)).

### Acknowledgeable Codes

`acknowledgeable` is a root list of validator codes that a source
[`@allow(CODE)`](language.md#acknowledging-native-hazards) may acknowledge. The
shipped policy lists `REVIEWED_VALUE_TYPE_MISMATCH`,
`NATIVE_DEFECTIVE_EXPRESSION` and `EXPRESSION_METADATA_RETURN_TYPE_MISMATCH`.
Each entry must appear once and be one of the native hazard codes the
validator reports (`NATIVE_HAZARD_CODES` in `aa2modulus/core/diagnostics.py`), so
authoring checks such as type, scope or dependency findings cannot be listed.
An empty list makes every `@allow` an `ALLOW_NOT_PERMITTED` error.

### Preferred Names and Lookup

`preferred_names` assigns the one spelling of an action, expression or named
constant. Events keep their native symbols. For example:

```toml
[preferred_names.actions]
110 = "ClassStorage.SetInt"             # Set Class Storage Integer

[preferred_names.expressions]
"int:121" = "ClassStorage.GetInt"       # Get Class Storage Int
```

Names must be ASCII identifiers or contiguous dot-separated identifiers, with
no keyword segment. Dots are never flattened; `ClassStorage.GetInt` does not
create `ClassStorageGetInt`. A qualified name's first segment (the namespace root)
must start with an uppercase ASCII letter, roots are unique ignoring case, and
roots match case-sensitively in source. Later segments and unqualified names match
case-insensitively, and output keeps the configured spelling.

A target with a canonical spelling (a preferred name; for events, the native
symbol; for a card-first target, its [member form](#receiver-member-forms)) accepts only that spelling. Native record
names, normalized identifiers and interactive labels (`AddLikePoints`,
`NpcTalkTarget`, `CardAddedToClass`, the constant label `LOVE`) are not accepted
for it. A member-canonical target accepts no flat spelling at all: native
fallbacks and the former qualified names (`Character.SetVirtue`) are unknown
names, and the error hints at the member form (`use 'coach.SetVirtue(3)'` for
`Character.SetVirtue(coach, 3)`, or `use '<card>.Virtue'` without usable arguments). The catalog exposes the member as the target's single
canonical `SourceForm` (`kind == "member"`, `form.member` is the `MemberForm`);
`catalog.canonical_name` returns the member name and `catalog.member_form(kind,
identifier, scope)` the receiver projection. A target with no canonical spelling (grammar-owned branch and loop
actions such as `ElseValue`, payload markers, int:99) keeps its native record
names, so recovery is unaffected. The catalog records each retired spelling, and an
unknown action, expression, event, constant or member name equal to one adds
`; use '<canonical>'` to the error (all canonical names when several targets
share it). GUI templates and prose are kept as provenance and never normalized into
names. For example, `%p.SetStamina = %p`
does not introduce `PSetStaminaP`, and `Notification(text: %p, isImportant: %p)`
does not introduce `NotificationTextPIsImportantP`. Use `coach.SetStamina` and
`Notification`.

A preferred name that is the native name of a different target is a policy
error (validation checks raw native names, even when that target no longer
accepts them). Duplicate canonical signatures are rejected. Unqualified expressions try variables, then
zero-argument expressions, then named constants. Qualified built-ins bypass
variable lookup, including quoted variables containing dots.

The formatter uses a preferred name, or a deterministic registry fallback for a
target without a canonical spelling, only when that spelling resolves to the same
identity. Operators and control flow
take precedence. Raw provenance, unknown IDs, incompatible
signatures, and unresolved collisions stay raw. Named-constant targets require
explicit IDs and select their actual first native row, merging equivalent duplicates.
Conflicting row labels produce targeted diagnostics. Positional-only entries
remain available through raw forms and registry lookup.

### Naming Convention

Every canonical name follows one convention, so a name tells you its domain and
role. Source names are PascalCase ASCII identifiers; acronyms count as words
(`Npc`, `Pc`, `Lua`, `Csv`).

- **Shape.** A target whose native slot 0 is a card (213 actions and
  expressions: stats, personality, traits, relationship points, opinions, H
  stats, items, names, appearance, mood, style, preferences, modifiers, partners,
  grades, lovers, card storage, NPC commands on a card) is a member of that card
  and has no preferred name: `coach.SetVirtue(3)`, `coach.Virtue`. Every other
  action and expression is `Root.Name`; named constants and literals are
  `Constants.Category.UPPER_SNAKE`. There is no `Character` root.
- **Roots** (case-sensitive):
  - `Npc`: card-less NPC commands and checks (action-kind predicates, poses).
  - `Context`: values and settable response state of the current event.
  - `Conversation`: PC conversation state, lines, actors and responses.
  - `H`: H-scene state and control.
  - `Globals`: game- and class-wide state (days, periods, player character,
    timers, seats, clubs, class membership).
  - `ClassStorage`, `Lua`, `Math` (random, roll) and `Text` (string functions).
  - `Constants`: named constants.
- **Core names are unqualified**: `ThisCard`, `TriggeringCard`, `Notification`, `WriteLog`,
  `StopThread`, `StopThreadIf`, `JumpIf`, and the conversions `ToInt`, `ToFloat`
  and `ToString`.
- **Verbs.** A getter is a noun (`coach.Virtue`). Its setter is `Set` plus the
  same noun (`coach.SetVirtue`). Increments are `Add...`,
  removals `Remove...`. Boolean possession, relation or property getters read as
  predicates (`Has...`, `Is...`: `coach.HasGlasses` pairs with
  `coach.SetGlasses`); setting-like flags keep the noun (`Globals.AutoPc`).
  Response percentages end in `Chance`; one-argument totals start with `Total`.
- **Overloads** differ only by parameter types with the same meaning (`ToInt` for
  float and string). Never overload by result type alone: `Lua.CallInt`,
  `Lua.CallBool`, `Lua.CallFloat` and `Lua.CallString` stay distinct. Actions
  cannot overload.
- **Members.** The member name is the canonical spelling of a card-first target;
  the receiver is the card in slot 0: `actor.AddLike(target, 30)`. Argument names
  are camelCase forms of the native template labels.
- **Constants.** Categories are singular PascalCase (`Relationship`,
  `Conversation`, `Trait`, `Day`, `Period`, `PregnancyRisk`, `EventType`, `Mood`,
  `Preference`, `Opinion`, `Room`) and the last segment is `UPPER_SNAKE`:
  `Constants.Mood.JEALOUS`, `Constants.Room.SCHOOL_GATES`.
- **Events keep their native symbols** (`on CARD_ADDED;`). Event-type constants
  use the native category name `EventType` (`Constants.EventType.KEY_PRESS`).
- Native spellings (`AddLikePoints`, `NpcTalkTarget`) are not accepted for a
  target with a preferred name or member form.

### Readable Expressions

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

A readable target needs a preferred name. The marker permits readable output
without changing the BOOL native declaration or suppressing native validation
errors. If the native declaration is corrected, loading fails until the marker is
removed, so stale exceptions cannot linger.

### Native Defects

`[defects]` records native targets that cannot work in AAUnlimited as pinned.
Every use reports `NATIVE_DEFECTIVE_EXPRESSION` (an error under strict
validation, a warning under `profile="native"`) with the recorded reason; the
target still parses, decodes, formats and keeps its name, so existing binaries
stay recoverable:

```toml
[defects.expressions]
"string:13" = { declared = ["int", "int", "int", "string"], reason = "its first parameter is declared int, but ..." }
```

`declared` must equal the registry's parameter types. A regenerated registry
with a corrected declaration fails to load until the entry is reviewed and
removed. The fix belongs upstream; the toolchain never repairs these targets.
Every validation path reports defects, including `validate_module(module)`
without a `catalog` and `compile_module`, which load the shipped policy.
Evidence for STRING/13
(`Text.Replace`) is [N12](native-format.md#native-source-evidence).

### Event Values

`[event_values.expressions]` lists expressions whose native callback reads
event data, so the value exists only during some events. Each type key (`int`,
`bool`, `float`, `string`) lists the event IDs in which the callback returns
event data of that type; in every other event it returns `otherwise`, whose
TOML type selects the wire type:

```toml
[event_values.expressions]
"int:100" = { callback = "Thread::GetNpcResponseOriginalAnswer", int = [8], otherwise = false }
```

Validation reports a use whose type differs from the event's type
(`REVIEWED_VALUE_TYPE_MISMATCH`) and a trigger without a fully known event
(`REVIEWED_VALUE_CONTEXT_UNKNOWN`); see the [language reference](language.md).
`callback` must equal the registry's implementation symbol, so a regenerated
registry that changes it fails to load until the entry is reviewed. Every
listed event must exist, and no event may appear under two types. Evidence:
[N6, N7 and N11](native-format.md#native-source-evidence).

### Result Roles

`[result_roles.expressions]` says what an expression's value means, using the
same role words as member receivers and arguments:

```toml
[result_roles.expressions]
"int:11" = "card"   # GetNpcResponseTarget: answeredTowards (a seat), else -1
"int:103" = "card"  # GetTarget: also the member property coach.Target
```

A role must be one that some member receiver or argument already uses with the
expression's result type (`card` is an `int` role); unknown targets and payload
markers are rejected. The key is the native expression, so the role applies to
every spelling, including member properties. Role `card` types the result as the
source type [`card`](language.md#cards): it is accepted where a card is expected,
while an untagged `int` there needs `Card(...)`. The wire type stays `int`.
Hover shows `Returns: card` and signatures `-> card`; completion ranks card
values first where a card is expected. Other roles would be documentation only.
The default policy tags 16 seat-valued expressions, each with its pinned-source
evidence in a comment. `Context.NpcTalkTarget`, `Context.NpcTalkAbout` and
`Context.RelationshipTowards` return 0, a valid seat, outside their events;
context checks report those reads, so they are cards too (owner, 2026-10-17).

### Parameter Names

`[parameter_names.actions]` and `[parameter_names.expressions]` name every
native parameter slot of a target that is not a member:

```toml
[parameter_names.actions]
51 = ["pc", "partner"]                 # H.Start

[parameter_names.expressions]
"int:121" = ["key", "fallback"]        # ClassStorage.GetInt
```

The list length must equal the native parameter count; names are distinct,
unqualified non-keyword identifiers. Member targets are rejected here because
their `[members]` arguments already name them. Native `interactive_name`
labels are GUI text and are not parsed (several use reserved words such as
`default`, `from` and `to`). Names are editor data only: hover, signature
help, the generated reference and `builtins.json` show them; binding and
output are unchanged. The default policy names all 104 non-member
parameterized targets that have a source spelling (actions 1 and 9 are
structural and have none).

### Parameter Roles

`[parameter_roles.actions]` and `[parameter_roles.expressions]` give roles to
named slots of non-member targets, keyed by their `[parameter_names]`:

```toml
[parameter_roles.actions]
51 = { pc = "card", partner = "card" }      # H.Start: Thread::StartHScene

[parameter_roles.expressions]
"bool:16" = { seat = "card" }               # Globals.IsSeatFilled
```

Each name must be one of the target's `[parameter_names]`, and the role one that
some member receiver or argument already uses with the slot's type. Role `card`
types the slot as a source `card`, so an `int` argument other than a literal or
constant needs `Card(...)`. The default policy tags the seat slots of actions 51,
91, 119 and 120 and `bool:16`; each reads the slot as a seat and checks it with
`ActionSeatInvalid`/`ExpressionSeatInvalid` in pinned `Actions.cpp`/`Expressions.cpp`.
Actions 119/120 pass that seat to `GameState::kickCard`/`addCard`. Signature help and the generated
documentation show `seat: card`.

### Descriptions

`[descriptions.expressions]` replaces a native expression description wherever
it is shown (hover, completion, signature help, the generated reference and
`builtins.json`). Keys use the `"type:id"` target notation. Text is trimmed and
must not be empty:

```toml
[descriptions.expressions]
"string:13" = "Does not work in AAUnlimited: ..."
```

The shipped tables override only `Text.Replace` (STRING/13), whose description
warns that it does not work ([native defects](#native-defects)); every other
target uses its native description.

### Receiver Member Forms

`[members]` entries configure the canonical spelling of one card-first native
action or expression: `receiver.Member(arguments)`, or the property
`receiver.Member` when an expression has no explicit arguments. Keys use target
notation; each value is a signature string of the member name and its
`name: role` arguments:

```toml
[members.actions]
13 = "AddLike(towards: card, amount: points)"   # Add Like Points
88 = "CancelAction"                             # no arguments

[members.expressions]
"int:25" = "Virtue"                             # coach.Virtue
```

The member name and argument names are unqualified non-keyword identifiers;
`Name()` equals `Name`. The receiver is always a `card` and fills native slot 0;
the arguments fill slots 1..n in order, so the argument count
must be one less than the native parameter count. The signature and result type
come from the native target. The initial contract accepts only a slot-0 `int`
receiver, targets without structured (`invalid`) parameters or payload markers,
and at most one form per spelling, target kind and argument count; one name may
therefore have both an action and an expression form. Trailing defaults, permuted
slots and dropped or duplicated receivers are not expressible. Role `card`
types the receiver or an argument as the source type
[`card`](language.md#cards) (still an `int` on the wire); other roles are
documentation and completion data. The default policy
configures 213 members (98 actions, 115 expressions), one for every card-first
action and expression. A member target has no preferred name (policy validation
rejects both on one target), so the member is its only source spelling and the
spelling the formatter and decompiler write. A bare built-in is also a receiver
when it is a registered zero-argument `int` expression (`ThisCard.Virtue`,
`TriggeringCard.AddLike(...)`). Static
namespace roots (first segments of every configured qualified name, matched
case-sensitively) remain the binder's first interpretation of a dotted token;
see [Receiver Calls](language.md#receiver-calls).

### Literal Source Values

`[literals]` gives qualified names to values of named-constant rows that their
own ID cannot select, because an earlier row shares the ID:

```toml
[literals]
"Constants.Room.SCHOOL_GATES" = { row = "School gates", value = 0 }
"Constants.Period.EXAM"       = { row = "EXAM", value = 11 }
```

`row` is the native row name; add `category = "..."` when the name occurs more
than once in the scope. The TOML type of `value` selects the scope (`0` is int,
`0.0` float, `false` bool, `"x"` string). The value must equal the row's verified
value, and the row must still be shadowed: if its own ID ever selects it, use the
native constant instead. A literal name cannot collide with a native getter or
named constant. Twelve defaults cover the shadowed room rows and
`Constants.Period.EXAM`; `Constants.Room.SCHOOL_GATES` lowers to INT/0. They
lower through BoundLiteral, while native references retain their wire IDs.
Literal recovery remains numeric.

### Defining an Action Default

Defaults fill trailing serialized action parameters. The table key is the action
ID, each entry key is a parameter index, and the TOML value type selects the
wire type:

```toml
[action_defaults.108]  # Notification
1 = false
```

This lets `Notification("Loaded")` lower to `Notification("Loaded", false)`.
Binding inserts the value before lowering. The loader rejects unknown actions,
out-of-range or non-trailing parameters, and values of the wrong type.

Only use defaults supported by native behavior. The selected default is
`false` for `Notification`'s `isImportant` parameter. Other actions require
their full declared arguments: a zero or false value may change state, and
runtime behavior such as an optional emitted event does not make a source
argument optional. Expressions have no source-level optional parameters;
storage getter fallback values remain explicit.

## Float Wire Policy

The serializer stores raw IEEE-754 binary32 values. Preserve signed zero,
subnormals, infinities, and NaN payload bits. Use `float_bits(0xHHHHHHHH)` when
exact bits matter; formatting emits it for unusual decoded values. The logical
IR retains unusual bits as a model annotation; ordinary finite values keep the
`{type, value}` shape.

### Adding an Operator

`[operators]` maps each grammar token to the native expressions it may lower to,
one per signature:

```toml
[operators]
"+" = ["int:5", "float:5", "string:8"]   # string + string concatenates
```

The loader takes each expression's signature from the registry and its syntax
from the fixed table above. Prefix tokens need one-parameter expressions; infix
tokens need two. A token may not map two expressions with the same signature,
and serialized payload-marker IDs cannot be operator targets. Tokens outside the
grammar are rejected.

## Validation Workflow

### Portable language and metadata reference

Export standalone documentation from committed metadata and policy, without
reading the reference checkout. The repository keeps no copy; the bundle is
source material for a future website, so the destination is required:

```bash
python tools/export_reference.py --output-dir /path/to/site/reference
python tools/export_reference.py --output-dir /path/to/site/reference --check
```

These are toolchain maintenance commands; consuming the bundle requires no
Python package or generator. It contains grammar/language/policy guides, exact
parser grammar, examples with transitive libraries, native Markdown reference,
and machine-readable `reference.json`. Every action, event, type-scoped
expression and named-constant record includes IDs, signatures, descriptions,
categories, spellings, collisions, defaults, operators, native
values and provenance hashes. Duplicate constants retain their original scoped
positions and separate anchors.

The generated Markdown leads with candidate source names and signatures,
including policy defaults and the source `card` type. JSON type records retain
native `int` types with separate card roles. Native names and GUI labels remain separately
labeled facts. Machine-readable schema `aa2modulus.language-reference.v8` uses
`source_names.candidates` and includes fact/catalog fingerprints, registration
provenance, resolved values, policy event values and all constant wire lookups.
It also records readable expressions, expression result roles
(`result_role`), policy parameter names (`parameter_names`) and roles
(`parameter_roles`) and description overrides (`policy_description`,
shown instead of the native description), receiver forms (per
record and top-level `receiver_forms`) and verified literal source values,
and preserves every duplicate row anchor. Binder, formatter, editor and exporter
query the same catalog. Candidate membership still depends on actual argument,
type and scope context; readable forms do not establish native execution safety.
GUI placeholders never become generated source spellings; interactive labels
that are already valid identifiers remain policy candidates.

`--check` reports missing, stale and extra files. Export writes known files and
preserves unexpected files; review an obsolete file before removing it. Treat
the destination as a documentation bundle directory. These maintenance commands
are outside pytest and `mise run verify`; a consumer's copy changes only through
explicit export.

`aa2modulus editor-data catalog [--output <path>]` writes the editor's built-in
documentation, `builtins.json` (schema
`aa2modulus.editor-builtins.v1`), from the same catalog: canonical names,
signatures with parameter names and roles, descriptions (overrides first),
value events from policy `[event_values]`, and one placeholder example per entry.
Every example is compiled in a trigger for one of its value events; the export
reports omitted examples (currently INT/100, whose native declaration is BOOL),
targets skipped for lack of a source spelling, and parameterized targets without
names on stderr. The file is never hand-edited; better documentation comes from better policy data.

After editing the policy, run `mise run test -m metadata`; use `mise run verify` for
the full suite. Metadata tests exercise shipped spellings through compilation,
policy effects, and representative resource-loading failures. Programmatic policy
objects and custom registries are internal maintenance facilities, not a supported
Python embedding API. Runtime commands use package-local catalogs without
a source checkout; regeneration remains a manual `mise run registry --source-root <dir>` operation.
