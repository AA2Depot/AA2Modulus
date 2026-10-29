# Native format and runtime evidence

This page records what the binary module format and the AAUnlimited runtime
do, and where the pinned source shows it. The implementation is the code in
`aa2modulus/binary/` and `aa2modulus/model/`; this page indexes the native
evidence behind it. Generated registry facts are in
[metadata](metadata.md#generated-registry-facts), and source semantics in the
[language contract](language-contract.md).

The pinned revision is `312c658b256f41771a5488fbf79a677d7b4551a8` of the
[AAUnlimited source](https://github.com/aa2g/AA2Unlimited). Runtime code and
packaged resources never read a checkout of it; only
`tools/generate_registry.py` does, to regenerate the registry. The pointers
below are `file:line` in that revision, relative to the checkout root, and the
line numbers hold only for that revision. `Functions/` stands for
`AAUnlimited/Functions/` and `Triggers/` for
`AAUnlimited/Functions/Shared/Triggers/`. Every claim here comes from reading
the source. Nobody has run these checks against the game itself (Windows,
MSVC build).

## Target build and files

- The target is the Win32 Unicode build. `AAUnlimited/AAUnlimited.vcxproj`
  declares `Debug`, `Release` and `ReleaseDebug` for Win32 as a
  `DynamicLibrary` with `CharacterSet` Unicode and toolset `v140` (VS2015).
  The x64 configurations are an `Application` with `MultiByte`. They are not
  the target, and compatibility with them is untested. The Win32 Unicode
  target is why strings are UTF-16LE and `int`, `DWORD` and `float` take 4
  bytes.
- Module files have no extension. AAEdit lists every file that is not a
  directory in the override `module\` directory (`AAUnlimited/defs.h:14`;
  `Functions/AAEdit/UnlimitedDialog.cpp:3893-3910`) and exports modules there
  (`Functions/AAEdit/UnlimitedDialogParts/Triggers.cpp:758-762`). AAPlay
  replaces a module embedded in card data with the file of the same name in
  `data\override\module\<name>` under the AAEdit path
  (`Functions/AAUCardData.cpp:65-90`). So the compiler writes an extensionless
  path.

## Primitive encoding

Every value is a raw little-endian copy, with no padding, tags or alignment
(`Functions/Serialize.h`, `Files/ModuleFile.cpp`).

```text
int32 / uint32 / enum   4 bytes        Types and counts too
bool                    1 byte         reader: nonzero is true; writer emits 0 or 1
float32                 4 bytes        IEEE-754 binary32; exact bits preserved
wstring                 uint32 code_unit_count + uint16[count]   UTF-16LE, no terminator
vector<T>               uint32 element_count + elements
```

A string's count is in UTF-16 code units, and bytes are twice that
(`Serialize.h:144-152`, `362-371`). The reader decodes with `surrogatepass`,
so unpaired surrogates survive a round trip. The model keeps the exact
binary32 bits of unusual floats (see
[Float Wire Policy](metadata.md#float-wire-policy)).

## Layout record

`Types` is `INVALID=0, INT=1, BOOL=2, FLOAT=3, STRING=4, N_TYPES=5`
(`Triggers/Value.h:9-14`). `N_TYPES` is never a valid serialized type. The
expression payload markers are `EXPR_CONSTANT=1`, `EXPR_VAR=2` and
`EXPR_NAMEDCONSTANT=3` (`Triggers/Expressions.h:52-54`).

```text
Module        := wstring name; wstring description;
                 vector<Trigger> triggers; vector<GlobalVariable> globals;
                 vector<wstring> dependencies
Trigger       := wstring name; vector<Event> events;
                 vector<Variable> vars; vector<GUIAction> guiActions
GUIAction     := Action action; vector<GUIAction> subactions        # recursive tree
Event         := int32 event_id;  vector<Expression> actualParameters
Action        := int32 action_id; vector<Expression> actualParameters
Expression    := Types return_type; int32 expression_id; payload
payload       := Value                       # id == EXPR_CONSTANT
               | wstring variable_name       # id == EXPR_VAR
               | int32 named_constant_id     # id == EXPR_NAMEDCONSTANT
               | vector<Expression>          # any other id (function call)
Value         := Types type; payload
payload       := int32 | uint8 | float32 | wstring | none    # INT BOOL FLOAT STRING INVALID
Variable      := Types type; wstring name; Expression defaultValue
GlobalVariable:= Types type; wstring name; Value defaultValue;
                 Value currentValue; bool initialized
```

Only the payload branch chosen by the expression ID or value type is written;
the other branches are alternatives, not extra fields. A GUI action is one
action record followed by its child vector, and that tree is how control flow
is serialized. The model uses slightly different names (`variables`,
`gui_actions`, `children`, `parameters`). Before allocating, the reader checks
each vector count against the smallest possible encoded element: event 8,
expression 8, GUI action 12, variable 16, trigger 16, global 17 and dependency
string 4 bytes.

Sources: Module `Serialize.h:316-326`, Trigger `200-209`, Event `211-219`,
Action `221-228`, GUIAction `230-241`, Expression read `243-268` and write
`432-449`, Variable `270-278`, GlobalVariable `280-290` and write `459-467`,
Value `292-314`.

### Not serialized

These fields exist only at runtime and must never be written:
`Trigger::globalVars`, `owningCard`, `broken`, `bInitialized`, the flat
`actions` list, the GUI `parent` pointers (rebuilt on load), and
`Variable::id` and `GlobalVariable::id` (`Triggers/Triggers.h`).
`Trigger::Initialize()` (`Triggers/Triggers.cpp:195`) rebuilds the flat action
list and the variable indices from the GUI tree. The Python model has none of
these fields; flattening exists only as a test projection.

## No header, no trailing-byte check

The file has no magic number, version, padding, checksum or trailer, and none
may be added without evidence from the serializer. `ModuleFile::FromFile()`
reads the whole file, decodes a `Module` and sets `good` without comparing the
bytes it consumed with the bytes available (`Files/ModuleFile.cpp:29-30`), so
the game ignores trailing bytes. This tool reports them as `TrailingBytes`
(`decode_module`) or rejects them (`reject_trailing`, `inspect --strict`). That
is deliberate hardening beyond native behaviour. An empty or unreadable file,
or a truncated buffer, leaves `good` false (`ModuleFile.cpp:11-37`).

Two more deliberate differences:

- For an unknown `Value` type ID, the native reader reads no payload
  (`Serialize.h:309-311`). This reader fails with `unknown Value type id`.
- Unknown event, action and expression IDs give null registry pointers in the
  game. The model keeps the raw IDs, and the writer emits them unchanged
  without metadata.

## Lookups and identity

- `Event::FromId(id)` and `Action::FromId(id)` index `g_Events[id-1]` and
  `g_Actions[id-1]`. IDs below 1 or past the end return null
  (`Triggers/Event.h:82-86`, `Triggers/Actions.h:74-78`).
- `Expression::FromId(type, id)` indexes `g_Expressions[type][id-1]`
  (`Triggers/Expressions.h:86-90`). The type scope is part of the identity, so
  never resolve an expression by ID alone.
- `NamedConstant::FromId(type, id)` returns the first row whose explicit `id`
  matches, and only then falls back to the 1-based position
  (`Triggers/NamedConstant.h:45-53`). The wire stores only the integer ID, and
  native lookup scopes it by the expression's return type. When the game saves
  a module, it writes the matched row's explicit `id` and the return type the
  registry declares for the expression, whatever the file said before
  (`Serialize.h:432-449`).

### Duplicate named-constant IDs

The pinned registry has 365 int constant rows with 352 distinct explicit IDs,
in 13 duplicate groups. Checked against
`aa2modulus/metadata/registry/named_constants.json`:

| Wire id | Rows | Native lookup |
| --- | --- | --- |
| 298-308 | event record (ordinals 191-201), then room record (310-320) | The event record wins. Room labels cannot select their room value through that ID |
| 282 | two equivalent `Opinion70` rows, value 73 | Same meaning; one native reference |
| 352 | `HOMEROOM` (value 2), then `EXAM` (value 11) | `HOMEROOM` wins |
| 353-365 | no row has these explicit IDs, so lookup falls back to position | Positions 353-365 hold rows with explicit IDs 341-352. A re-save writes the row's explicit ID, so wire 365 (the `EXAM` row) reloads as `HOMEROOM` |

Recovery keeps the original wire IDs and never picks a fallback ID to fix a
name. Source-level handling is in
[metadata](metadata.md#preferred-names-and-lookup).

## Native source evidence

| # | Claim | Pinned pointer |
| --- | --- | --- |
| N1 | Variables resolve globals first, then locals, without comparing declaration types. Set Variable compares the two serialized expression return types. Evaluation returns the stored value | `Triggers/Triggers.cpp:229-255`, `264-290`, `339-354`; `Triggers/Thread.cpp:90-107` |
| N2 | IF, ELSEIF and ELSE children are flattened with fresh loop state. Break and Continue emit jumps only when a patch list exists | `Triggers/Triggers.cpp:41`, `74`, `169-185` |
| N3 | Adding a module merges the module globals the card lacks into card data and keeps card globals with the same name. Triggers of card modules are initialized with that card's globals | `Functions/AAUCardData.cpp:1440-1476`; `Functions/AAPlay/Globals.cpp:39-48` |
| N4 | Dependencies: see [dependency evidence](#dependency-evidence) | below |
| N5 | `NamedConstant::FromId` checks explicit IDs first | `Triggers/NamedConstant.h:45-53` |
| N6 | INT/100 is registered in the INT vector but declared BOOL. Its callback returns INT under NPC_RESPONSE. Initialization compares the declared type, and a native save writes BOOL/100 | `Triggers/Expressions.cpp:3708-3715`, `2391-2395`; `Triggers/Event.h:155-165`; `Triggers/Triggers.cpp:278`, `303`, `318`, `347`, `356`; `Functions/Serialize.h:243-268`, `432-449` |
| N7 | The INT/101 and INT/70 callbacks return different tags depending on the event. INT/99 is a placeholder that returns -1 | `Triggers/Expressions.cpp:2430-2433`, `2906-2919`, `3530-3533`, `2563-2566`, `3704-3707` |
| N8 | INT/62 (`PC ConversationId`) is registered. Action 17 (native name `Conditional End Execution`, policy name `StopThreadIf`) calls `ConditionalEndExecution`, which sets `execFinished` when its bool is true | `Triggers/Expressions.cpp:3482-3485`; `Triggers/Actions.cpp:34-38`, `2353-2358` |
| N9 | Action 13 has three INT parameters. `AddCardLikePoints` reads slot 0 (from seat), 1 (towards seat) and 2 (points) | `Triggers/Actions.cpp:292-298`, `2323-2327` |
| N10 | Description controls are `ES_MULTILINE`. Strings serialize as exact counted UTF-16 with no newline conversion. The CLI reads text with universal-newline translation, so a literal CRLF needs care when the file is read | `AAUnlimited/AAUnlimitedDll.rc:373`, `396`; `Functions/Serialize.h:144-152`, `362-371` |
| N11 | A bool `Value` writes one byte of its `iVal`/`fVal`/`bVal` union. The evaluator passes callback results on without a type check, and `EqualsIntegers` compares `iVal`, so using a bool result as an INT reads unspecified upper bytes. Runtime observation (owner, 2026-10-15): `CurrentResponse` in `After NPC Response` read `1060439040` (`0x3F350400`), then `0`, in one run | `Triggers/Value.cpp:52-55`, `125-170`; `Triggers/Thread.cpp:136-148`; `Triggers/Expressions.cpp:350-352`, `2429-2433` |
| N12 | STRING/13 (`Replace substring`, policy name `Text.Replace`) declares parameters `(int, int, int, string)`, but `Thread::StringReplace` reads slot 0 as `*params[0].strVal`. Initialization rejects a string argument there, because an argument's return type must equal the declared parameter type. An int argument passes initialization but is read as a string pointer, so the expression cannot work. A negative `from` also computes `size - from` | `Triggers/Expressions.cpp:4564-4567`, `591-603`; `Triggers/Triggers.cpp:277-285` |
| N13 | Ordinary action and expression arguments are evaluated in ascending parameter order before the callback runs. An INVALID argument stops evaluation: the action is skipped, and the expression logs a warning and yields INVALID. BOOL/4 (and) and BOOL/5 (or) short-circuit left to right with no INVALID check. Other callbacks have not been reviewed | `Triggers/Thread.cpp:73-84`, `110-129`, `136-148` |

### Dependency evidence

- The exporter scans only action parameters, nested GUI children included. It
  never looks at event parameters or local default expressions, so a global
  used only there is missed (`Triggers/Module.cpp:16-109`; export in
  `Functions/AAEdit/UnlimitedDialogParts/Triggers.cpp:740-763`).
- A global belongs to the first attached module that declares its name. There
  is no dependency graph and no cycle handling. Dependency strings are read
  and written after the globals (`Triggers/Module.cpp:82-107`;
  `Functions/Serialize.h:324`, `502`).
- Loading never uses dependencies. `AddModule` adds missing globals and keeps
  the module entry (`Functions/AAUCardData.cpp:1440-1476`). Unpacking copies
  the triggers, then `RemoveModule` drops the module and keeps its globals
  (`Functions/AAEdit/UnlimitedDialog.cpp:3834-3845`,
  `AAUCardData.cpp:1478-1484`).
- The `Module` constructor assigns `this->dependencies = dependencies`, the
  member to itself (`Triggers/Module.cpp:12`); its purpose is unknown. Module
  triggers are read-only in the trigger UI
  (`UnlimitedDialogParts/Triggers.cpp:160-172`, `604-616`). The export
  dialog's preview leaves out globals, which affects only the UI.

## Corpus evidence

On 2026-10-06 the tool was audited against 727 known-working modules supplied
by users: 2,310 triggers, 23,388 GUI actions, a tree depth of 16 and 68
multiline descriptions. The corpus and the fixtures kept from it were retired
on 2026-10-07. Every module passed decoding, byte identity, source recovery
and recompilation.

The corpus contained no serialized dependencies (all 727 dependency vectors
were empty), no initialized globals, no name collisions between globals and
locals, no non-control actions with children, no unusual float bits, no
trailing bytes and no noncanonical booleans. Those paths rest on synthetic
tests and source reading, not on bytes the game produced. Four modules did
carry current global values that differed from the defaults.
