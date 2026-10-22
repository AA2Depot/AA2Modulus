# Native Format and Runtime Evidence

This page records what the binary module format and the AAUnlimited runtime do,
and where the pinned source shows it. The code in `aa2modulus/binary/` and
`aa2modulus/model/` is the implementation; this page is the index of native
evidence behind it. Generated registry facts are in [metadata](metadata.md#generated-registry-facts),
source semantics in the [language reference](language.md).

The pinned revision is `312c658b256f41771a5488fbf79a677d7b4551a8` of the
AAUnlimited source. Runtime code and packaged resources never read the
checkout; only `tools/generate_registry.py` does, to regenerate registry data. Pointers
below are file:line in that revision, relative to the checkout root. `Functions/`
is `AAUnlimited/Functions/` and `Triggers/` is `AAUnlimited/Functions/Shared/Triggers/`.
Line numbers are specific to this revision. All claims are source inspection;
native Windows/MSVC execution has not been run.

## Target Build and Files

- The target is the Win32 Unicode build: `AAUnlimited/AAUnlimited.vcxproj`
  declares `Debug|Release|ReleaseDebug` for Win32 as `DynamicLibrary`,
  `CharacterSet` Unicode, toolset `v140` (VS2015). The x64 configurations are
  `Application` with `MultiByte`; they are not the target, and compatibility with
  them is untested. This is why strings are UTF-16LE with 4-byte `int`/`DWORD`/`float`.
- Module files have no extension. AAEdit lists every non-directory file in the
  override `module\` directory (`AAUnlimited/defs.h:14`;
  `Functions/AAEdit/UnlimitedDialog.cpp:3893-3910`) and exports there
  (`Functions/AAEdit/UnlimitedDialogParts/Triggers.cpp:758-762`). AAPlay replaces a
  module embedded in card data by name from `data\override\module\<name>` under the
  AAEdit path (`Functions/AAUCardData.cpp:65-90`). The compile output is therefore
  an extensionless path.

## Primitive Encoding

All values are raw little-endian copies with no padding, tags or alignment
(`Functions/Serialize.h`, `Files/ModuleFile.cpp`).

```text
int32 / uint32 / enum   4 bytes        Types and counts too
bool                    1 byte         reader: nonzero is true; writer emits 0 or 1
float32                 4 bytes        IEEE-754 binary32; exact bits preserved
wstring                 uint32 code_unit_count + uint16[count]   UTF-16LE, no terminator
vector<T>               uint32 element_count + elements
```

The string count is in UTF-16 code units, not bytes (`Serialize.h:144-152`,
`362-371`). The reader decodes with `surrogatepass`, so unpaired surrogates
round-trip. The model carries exact binary32 bits for unusual floats (see
[Float Wire Policy](metadata.md#float-wire-policy)).

## Layout Record

`Types` is `INVALID=0, INT=1, BOOL=2, FLOAT=3, STRING=4, N_TYPES=5`
(`Triggers/Value.h:9-14`); `N_TYPES` is not a valid serialized type. Expression
payload markers are `EXPR_CONSTANT=1`, `EXPR_VAR=2`, `EXPR_NAMEDCONSTANT=3`
(`Triggers/Expressions.h:52-54`).

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

Only the payload branch selected by the expression id or value type is written;
alternatives are not extra fields. A GUI action is one action record followed by
its child vector; the tree is the serialized form of control flow. Model names
differ slightly (`variables`, `gui_actions`, `children`, `parameters`). The reader
checks vector counts against the minimum encoded element size (event 8, expression 8,
GUI action 12, variable 16, trigger 16, global 17, dependency string 4 bytes) before allocating.

Sources: Module `Serialize.h:316-326`, Trigger `200-209`, Event `211-219`,
Action `221-228`, GUIAction `230-241`, Expression read `243-268` and write
`432-449`, Variable `270-278`, GlobalVariable `280-290` and write `459-467`,
Value `292-314`.

### Not Serialized

These exist at runtime only and must not be written: `Trigger::globalVars`,
`owningCard`, `broken`, `bInitialized`, the flattened `actions` list; GUI `parent`
pointers (rebuilt on load); `Variable::id` and `GlobalVariable::id`
(`Triggers/Triggers.h`). `Trigger::Initialize()` (`Triggers/Triggers.cpp:195`)
rebuilds the flat action list and variable indices from the GUI tree. The Python
model has no such fields; flattening is a test projection only.

## No Header, No Trailing-Byte Check

There is no magic, version, padding, checksum or trailer; none may be added without
serializer evidence. `ModuleFile::FromFile()` reads the whole file, decodes a
`Module`, and sets `good` without comparing consumed and available bytes
(`Files/ModuleFile.cpp:29-30`). Trailing bytes are therefore ignored natively. This
tool reports them as `TrailingBytes` (`decode_module`) or rejects them
(`reject_trailing`, inspection `--strict`); that is deliberate hardening, not
native behavior. A zero-length or unreadable file, or a truncated buffer, leaves
`good` false (`ModuleFile.cpp:11-37`).

Other deliberate differences: native reading of an unknown `Value` type id reads no
payload (`Serialize.h:309-311`), while this reader fails with `unknown Value type id`;
unknown event/action/expression ids yield null registry pointers natively, while
the model keeps raw ids and the writer emits them unchanged without metadata.

## Lookups and Identity

- `Event::FromId(id)` and `Action::FromId(id)` index `g_Events[id-1]` and
  `g_Actions[id-1]`; ids below 1 or past the end return null
  (`Triggers/Event.h:82-86`, `Triggers/Actions.h:74-78`).
- `Expression::FromId(type, id)` indexes `g_Expressions[type][id-1]`
  (`Triggers/Expressions.h:86-90`). The type scope is part of the identity; never
  resolve an expression by id alone.
- `NamedConstant::FromId(type, id)` returns the first row with a matching explicit
  `id`, and only then the 1-based position (`Triggers/NamedConstant.h:45-53`). The
  wire stores only the integer id; native lookup scopes it by the expression's
  return type. Writing uses the registry row's explicit id and the registry's
  declared return type (`Serialize.h:432-449`), not the serialized tag.

### Duplicate Named-Constant IDs

The pinned registry has 365 int constant rows with 352 distinct explicit ids and
13 duplicate groups. Verified against `aa2modulus/metadata/registry/named_constants.json`:

| Wire id | Rows | Native lookup |
| --- | --- | --- |
| 298-308 | event record (ordinals 191-201), then room record (310-320) | event record wins; room labels cannot select their room value through that id |
| 282 | two equivalent `Opinion70` rows, value 73 | same meaning; one native reference |
| 352 | `HOMEROOM` (value 2), then `EXAM` (value 11) | `HOMEROOM` wins |
| 353-365 | no explicit id; positional fallback | rows with explicit ids 341-352; a re-save writes that row's id, so wire 365 (`EXAM` row) reloads as `HOMEROOM` |

Recovery keeps the original wire ids; it never picks a fallback id to fix a name.
Source-level handling is in [metadata](metadata.md#preferred-names-and-lookup).

## Native Source Evidence

| # | Claim | Pinned pointer |
| --- | --- | --- |
| N1 | Variables resolve globals first, then locals, with no declaration-type comparison; Set Variable compares the two serialized expression return types; evaluation returns the stored value | `Triggers/Triggers.cpp:229-255`, `264-290`, `339-354`; `Triggers/Thread.cpp:90-107` |
| N2 | IF/ELSEIF/ELSE children are flattened with fresh loop state; Break/Continue emit jumps only when a patch list exists | `Triggers/Triggers.cpp:41`, `74`, `169-185` |
| N3 | Adding a module merges missing module globals into card data and keeps same-name card globals; triggers of card modules are initialized with that card's globals | `Functions/AAUCardData.cpp:1440-1476`; `Functions/AAPlay/Globals.cpp:39-48` |
| N4 | Dependencies: see [Dependency Evidence](#dependency-evidence) | below |
| N5 | `NamedConstant::FromId` explicit-first rule | `Triggers/NamedConstant.h:45-53` |
| N6 | INT/100 is registered in the INT vector but declared BOOL; its callback returns INT under NPC_RESPONSE; initialization compares the declared type; native save writes BOOL/100 | `Triggers/Expressions.cpp:3708-3715`, `2391-2395`; `Triggers/Event.h:155-165`; `Triggers/Triggers.cpp:278`, `303`, `318`, `347`, `356`; `Functions/Serialize.h:243-268`, `432-449` |
| N7 | INT/101 and INT/70 callbacks return mixed tags by event; INT/99 is a placeholder returning -1 | `Triggers/Expressions.cpp:2430-2433`, `2906-2919`, `3530-3533`, `2563-2566`, `3704-3707` |
| N8 | INT/62 (`PC ConversationId`) is registered; action 17 (native name `Conditional End Execution`, policy name `StopThreadIf`) calls `ConditionalEndExecution`, which sets `execFinished` when its bool is true | `Triggers/Expressions.cpp:3482-3485`; `Triggers/Actions.cpp:34-38`, `2353-2358` |
| N9 | Action 13 has three INT parameters; `AddCardLikePoints` reads slots 0 (from seat), 1 (towards seat), 2 (points) | `Triggers/Actions.cpp:292-298`, `2323-2327` |
| N10 | Description controls are `ES_MULTILINE`; strings serialize as exact counted UTF-16 with no newline conversion; the CLI itself reads text with universal-newline translation, so literal CRLF needs care at file reading | `AAUnlimited/AAUnlimitedDll.rc:373`, `396`; `Functions/Serialize.h:144-152`, `362-371` |
| N11 | A bool `Value` writes one byte of its `iVal`/`fVal`/`bVal` union; the evaluator passes callback results on without a type check, and `EqualsIntegers` compares `iVal`, so an INT use of a bool result reads unspecified upper bytes. Runtime observation (owner, 2026-10-15): `CurrentResponse` in `After NPC Response` read `1060439040` (`0x3F350400`), then `0`, in one run | `Triggers/Value.cpp:52-55`, `125-170`; `Triggers/Thread.cpp:136-148`; `Triggers/Expressions.cpp:350-352`, `2429-2433` |
| N12 | STRING/13 (`Replace substring`, policy name `Text.Replace`) declares parameters `(int, int, int, string)`, but `Thread::StringReplace` reads slot 0 as `*params[0].strVal`. Initialization rejects a string argument there (actual return type must equal the declared parameter type), and an int argument passes initialization but is read as a string pointer, so the expression cannot work. A negative `from` also computes `size - from` | `Triggers/Expressions.cpp:4564-4567`, `591-603`; `Triggers/Triggers.cpp:277-285` |
| N13 | Ordinary action and expression arguments are evaluated in ascending parameter index before the callback runs. An INVALID argument stops evaluation: the action is skipped, and the expression logs a warning and yields INVALID. BOOL/4 (and) and BOOL/5 (or) short-circuit left to right with no INVALID check. Other callbacks are unreviewed | `Triggers/Thread.cpp:73-84`, `110-129`, `136-148` |

### Dependency Evidence

- The exporter scans only action parameters (nested GUI children included), never
  event parameters or local default expressions; a global used only there is
  missed (`Triggers/Module.cpp:16-109`; export in `Functions/AAEdit/UnlimitedDialogParts/Triggers.cpp:740-763`).
- A global belongs to the first attached module that declares its name; there is no
  graph or cycle handling, and dependency strings are read and written after the
  globals (`Triggers/Module.cpp:82-107`; `Functions/Serialize.h:324`, `502`).
- Loading never consumes dependencies: `AddModule` adds missing globals and keeps the
  module entry (`Functions/AAUCardData.cpp:1440-1476`). Unpacking copies triggers and
  then `RemoveModule` drops the module but keeps its globals
  (`Functions/AAEdit/UnlimitedDialog.cpp:3834-3845`, `AAUCardData.cpp:1478-1484`).
- The `Module` constructor assigns `this->dependencies = dependencies` to itself
  (`Triggers/Module.cpp:12`); its purpose is unknown. Module triggers are read-only
  in the trigger UI (`UnlimitedDialogParts/Triggers.cpp:160-172`, `604-616`). The
  export-dialog preview omits globals; this is UI only.

## Corpus Evidence

On 2026-10-06 the tool was audited against 727 user-supplied, known-working modules
(2,310 triggers, 23,388 GUI actions, tree depth 16, 68 multiline descriptions);
the corpus and its retained fixtures were retired on 2026-10-07. Decode, byte
identity, source recovery and recompilation passed for every module. The modules
did **not** contain: serialized dependencies (all 727 dependency vectors are
empty), initialized globals, global/local name collisions, non-control actions with
children, unusual float bits, trailing bytes, or noncanonical booleans. Those paths
rest on synthetic tests and source inspection, not on native-produced bytes. Four
modules did carry current global values different from the defaults. Native
Windows/MSVC execution was never run, so every claim above is source evidence.
