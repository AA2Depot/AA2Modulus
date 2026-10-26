# Language server

The shared CLI provides diagnostics, completion, hover, signature help,
go-to-definition, document symbols, references, occurrence highlights, rename,
semantic highlighting, parameter-name inlay hints and quick fixes for `.aa2m`
modules and `.aa2mi` libraries.
Use an editor's existing LSP client or the VS Code extension, which lives in
its own repository (`aa2modulus-extension`) and owns its setup and
troubleshooting. The [client contract](#client-contract) lists the wire facts
any client relies on.

## Launch

Prepare the environment using [development setup](../README.md#quick-start),
then configure the client to run:

```bash
python -m aa2modulus lsp-server
```

Run from this checkout with its managed interpreter. For example, the launch
settings an LSP client needs are:

```json
{
  "command": "/path/to/aa2modulus/.venv/bin/python",
  "args": ["-m", "aa2modulus", "lsp-server"],
  "cwd": "/path/to/aa2modulus"
}
```

For a [standalone executable](standalone.md), use its absolute path with
`["lsp-server"]` arguments; it can run from any working directory:

```json
{
  "command": "/path/to/aa2modulus",
  "args": ["lsp-server"]
}
```

On Windows use `aa2modulus.exe`, or `.venv/Scripts/python.exe` for source-tree
launches. Register `.aa2m` with language ID `aa2m`. Saved `.aa2mi` libraries can
use `aa2m` or `aa2mi`; the starter uses `aa2mi` for saved and untitled libraries.
An untitled library must use language ID `aa2mi`. If the client requires a
different working directory, put the checkout on its `PYTHONPATH`.

The client owns the process and connects through stdin/stdout. Log messages use
stderr. `lsp-server --help` and `lsp-server --version` exit without opening a
session; `--version` prints the `serverInfo.version` sent at `initialize`
([version](development.md#version)). There are no transport flags. The
[standalone guide](standalone.md) records tested platforms and build recipes;
[roadmap](../plans/ROADMAP.md) limits apply.

## Authoring behavior

- Diagnostics use the same strict compiler checks, including imported errors
  and macro/template origins. A file with syntax errors shows each independent
  one (up to 25), but no binding errors until the syntax is clean. A shared library error appears once, retaining
  the related locations from each open root.
- Unsaved library buffers take precedence over disk. Edits and closes refresh
  dependent open roots; observed disk imports are checked every second. Missing
  libraries remain observed so creating them can refresh diagnostics.
- A closed `file:` document keeps its diagnostics: the server re-checks it from
  disk (reusing the last result when the buffer matched disk) and follows disk
  changes until it is reopened, deleted or unreadable. Untitled or unsaved-new
  files clear on close. Files never opened get no diagnostics; only references
  and rename read them ([below](#references-and-rename)). Closed files get no
  hover, completion or other authoring results.
- Hover and definition use the binder's selected declarations and metadata.
  Built-ins show signatures, descriptions, and policy defaults. Definitions
  navigate to authored variables, macro parameters/calls, template slots/uses,
  and import targets. Generated template-local names stay out of the outline.
- Completion and signature help use the existing grammar for incomplete
  prefixes, respect comments/strings and nested calls, and replace exact name
  tokens. A separate bounded editor view recovers completed declarations and
  successful binder selections around unfinished statements and imported files.
  It permits 32 syntax faults plus the ordinary source/import budgets; strict
  diagnostics and compilation still use the original input. Earlier-buffer
  locations are never reused. Suggestions respect statement/value/event context,
  declaration scope and known expected types, retaining distinct overloads.
- Conditions and boolean value slots also offer operands for comparisons before
  the comparison operator is typed. For example, `if (Globals.` offers
  `Globals.CurrentDay`; complete the condition with `== 1` or another comparison.
  Direct `!` operands remain boolean, and known comparison/argument types narrow
  candidates. Unknown complex operand types stay unrestricted. Literal-only
  global initializers and declaration name/type slots use their own grammar states.
- Namespace roots (`Globals.`, `Context.`) match case-sensitively. Card-first
  built-ins are members only and are never offered as flat names. After a
  receiver completion offers configured members: a variable (`coach.`),
  `variable("x").`, `(expr).`, a call result, a member chain (`coach.Target.`) or
  a bare zero-argument `int` built-in (`ThisCard.`, `TriggeringCard.`).
  Statement position lists action members, value positions list value members
  of the expected type. Properties (zero-argument values) insert without
  parentheses; calls insert the usual snippet. Only the member text is replaced.
  `Context.` still lists the `Context.*` built-ins. Signature help on any
  receiver lists the explicit arguments only. Hover and definition on a member
  or property name show `<card>.AddLike(towards: card, amount: int)` /
  `<card>.Target -> card` with the native description and open the built-in page.
- [Card](language.md#cards) values show their type: variables `coach: card`,
  card-valued built-ins (`ThisCard`, `Context.NpcTalkTarget`, `coach.Target`)
  `Returns: card` in hover and completion documentation, flat card slots
  `Globals.IsSeatFilled(seat: card)`. At the start of an argument that expects a
  card (`coach.AddLike(`, `Globals.IsSeatFilled(`, a `card` macro formal),
  card-valued built-ins and `card` variables sort first and every other item
  keeps its order after them. Other positions are not ranked, and nothing is
  filtered by role (an `int` there stays offered; it needs `Card(...)`).
- Inside `@allow(` completion offers the policy's acknowledgeable hazard codes
  (kind EnumMember) not yet listed in that attribute. There is no quick fix that
  adds an `@allow`: bypassing a hazard is not recommended.
- Compile-time constants (`const`) complete in value positions with kind
  Constant and detail `const Name: type = value` (the resolved literal), filtered
  by the expected type like variables. Module constants are visible only in the
  module; top-level and imported-library constants are also visible in macro
  bodies and trigger templates. A name that is not an identifier inserts
  `const("Name")`; inside `const("` every visible constant name is offered and
  the typed text (through the closing quote) is replaced by the escaped name.
  Hover on a use or declaration shows `const Name: type = value`; definition
  jumps from any use (bare, `const("X")`, global initializer, constant-to-constant
  link, imported library constant) to the declaration name. Document symbols list
  top-level constants and module constants (as module children) with kind
  Constant.
- Zero-argument runtime expressions use property items and insert bare names;
  events use event items after `on`. Variable assignment targets appear in statement
  positions alongside actions/macros, and so do card receivers (card-valued
  built-ins, card variables and card formals), inserted without `;` so a member
  follows. Value slots of any type offer card receivers too, ranked after the
  values that match, because a card member can return every value type.
  Qualified edits replace the complete token, preserve existing
  calls/terminators, and retain full candidate filter text so a client can
  refine the original list as more characters are typed. Known calls
  with no remaining usable arguments suppress impossible value suggestions.
  Quoted, keyword or dotted authored variable names insert an explicit
  `variable("name")` reference so they bind to the declaration.
  A getter shadowed by an authored variable inserts an explicit empty call
  (never for the protected `ThisCard`/`TriggeringCard`, which variables cannot shadow);
  variable/constant values are excluded when completing an existing call's callee.
- A first authoring request waits for an existing in-flight analysis instead of
  scheduling duplicate analysis of the same buffer. New edits and import changes
  still invalidate results; a second request is unnecessary to obtain completion.
- Clients advertising snippet support receive required-argument placeholders;
  policy-default arguments are omitted. Existing call parentheses and arguments
  are preserved. The VS Code client opens parameter help after accepting a call.
- Adjacent leading `//` and `/* ... */` comments document authored declarations
  in hover and completion, including imported buffers. A blank line or intervening
  code ends the association. Comments remain absent from serialized modules.
- Position encoding defaults to UTF-16; clients can negotiate UTF-8 or UTF-32.
  Source spans retain their inclusive Unicode code-point contract internally.

The server uses bundled metadata/policy and the existing source budgets. It
does not read binary modules; a global that only another module declares is
undefined until declared. Formatting is not planned (revisit if users ask).

## References and rename

References (`textDocument/references`), occurrence highlights
(`textDocument/documentHighlight`) and rename (`textDocument/prepareRename`,
`textDocument/rename`) work on authored declarations: globals, `let` locals,
constants, macros, macro parameters, trigger templates and template slots. A
declaration's occurrences are its name plus every use the binder selected for
it: bare names, `variable("…")` and `const("…")`, assignment and `for` targets,
macro calls in any case, `import.trigger` template names and `slot` bindings at
instantiation sites. Strings, comments, built-ins, module and trigger names and
card-storage keys are never occurrences. While a file has errors, the editor
view's selections are used, as for hover.

- **Scope.** Imports accept only `.aa2mi` paths, so a declaration in any other
  file is searched in that file alone. A declaration in a saved library is
  searched across the workspace: on the first such request the server reads
  every `.aa2m`/`.aa2mi` file under the workspace folders (including folders
  added later), skipping hidden files and directories, up to 2,000 files; a
  warning says when the cap is reached. Closed files are read from disk, with
  open buffers overriding their imports. Their analyses are cached and reused
  only while the file and every input it read are unchanged. A client that
  supports dynamic `workspace/didChangeWatchedFiles` registration receives a
  `**/*.{aa2m,aa2mi}` watcher, and created or deleted files trigger
  rediscovery; other clients are rediscovered on every such request. A request
  with a `workDoneToken` reports `$/progress` while uncached files are read.
  Without a workspace folder, open documents and their imports are searched.
- **Highlights** cover the current document. Declarations, assignment targets
  and `for` targets are writes; other uses are reads.
- **Spelling.** A new name that is a non-keyword, unprotected identifier is
  written bare. Otherwise declarations and `for` targets are quoted
  (`let "my count": int = 0;`), variable uses become `variable("…")` and
  constant uses `const("…")`; quoted sites stay quoted. Macro and slot names
  must be identifiers, and `ThisCard`/`TriggeringCard` are refused.
- **Validation.** The server applies the edits in memory and re-analyzes every
  affected module and library. It refuses the rename, naming the conflicting
  location, when a renamed use would refer to another declaration or a built-in
  (shadowing), when another use would start referring to the renamed
  declaration, or when the edit introduces an error. A file that changed during
  the request returns `ContentModified`.
- **Output.** Renaming a macro, constant, parameter or slot leaves compiled
  output byte-identical. Renaming a template also writes the old name as the
  output name of each `import.trigger` that had none, so trigger names are kept.
  Renaming a global or local changes the serialized variable name; for a global
  the server warns that other modules on a card that read it keep the old
  name.

Edits use versioned `documentChanges` when the client supports them (closed
files have no version), and `changes` otherwise.

## Semantic highlighting

`textDocument/semanticTokens/full` colors a name by what the binder selected for
it, not by how it is spelled. The legend uses standard token types, so themes
color it without configuration:

| Name | Token type | Modifiers |
| --- | --- | --- |
| action or expression call (`WriteLog`, `ToInt`) | `function` | `defaultLibrary` |
| zero-argument expression (`Globals.CurrentDay`) | `property` | `defaultLibrary`, `readonly` |
| member call (`coach.SetVirtue(3)`, `coach.GetBool(…)`) | `method` | `defaultLibrary` |
| member property (`coach.Virtue`) | `property` | `defaultLibrary` |
| qualifier segments of a built-in (`Globals`, `Constants`, `Room`, `H`) | `namespace` | `defaultLibrary` |
| named constant (`Constants.Room.SCHOOL_GATES`) | `enumMember` | `defaultLibrary`, `readonly` |
| event after `on` | `event` | `defaultLibrary` |
| `ThisCard`, `TriggeringCard` | `variable` | `defaultLibrary`, `readonly` |
| global, local | `variable` | `declaration` at the name, `modification` at assignment and `for` targets |
| macro parameter, template slot | `parameter` | `declaration` at the name |
| `const` | `variable` | `readonly`, plus `declaration` at the name |
| macro, trigger template | `macro`, `class` | `declaration` at the name |

Quoted names (`variable("coach")`, `const("Tag")`, `param "text"`) are one
token over the quoted string. Unresolved names, raw forms, keywords, literals,
module and trigger names get no token, so a client's lexical colors remain; a
typo keeps its lexical color while its diagnostic reports it. While a file has
errors the editor view's selections are used, as for hover. A request waits for
the analysis of the current text, so tokens never come from an older version.
When an import changes under an unchanged document the server sends
`workspace/semanticTokens/refresh` once, if the client supports it. Range and
delta requests are not offered.

## Inlay hints

`textDocument/inlayHint` labels literal arguments with their parameter names
(`Notification("x", isImportant: true)`), as `Parameter` hints with right
padding. Literals are numbers, bools, strings, `float_bits(...)` and a literal
under `!`; computed arguments are never labeled. Names come from what the binder
selected for the call: a member form's explicit arguments (the receiver is never
labeled), the policy `[parameter_names]` of the chosen flat overload, or a
macro's parameters. No hint is shown when:

- the call has one parameter named `value` or contained in the callee name
  (`coach.SetStyle(2)`, `ThisCard.SetVirtue(3)`, `ToInt("1")`);
- a string literal fills a storage key (member role `key`, or a flat parameter
  named `key`): `ThisCard.GetBool("Tutor", fallback: true)`;
- the call is unresolved or raw.

While a file has errors the editor view's selections are used. Clients toggle
hints with their own setting (VS Code: `editor.inlayHints.enabled`); the server
has none.

## Quick fixes

Some diagnostics carry concrete edits behind their `help` line. The server
publishes them in the diagnostic's private `data` with the document version,
and `textDocument/codeAction` (kind `quickfix`) turns the echoed data into
edits without re-analysis; a fix for an older version is not offered. A
diagnostic with exactly one fix marks it preferred.

| Finding | Fix |
| --- | --- |
| flat card-first call (`SetVirtue(ThisCard, 3);`) | `ThisCard.SetVirtue(3);` (one per matching member form) |
| wrong-case namespace root (`context.npctalktarget`) | the whole canonical name `Context.NpcTalkTarget`; only the root (`globals.CurrentDay` to `Globals`) when the tail is already exact, unknown or ambiguous |
| assignment to a protected name (`ThisCard = 3;`) | `variable("ThisCard") = 3;` |
| `AMBIGUOUS_CONST` read | `const("K")` or `variable("K")`; an assignment target gets only `variable("K")` |
| an `int` where a card is expected (`n.SetVirtue(1)`, `coach == n`) | `Card(n)` |
| `UNDEFINED_VARIABLE` with a known type, such as a decompiled read of another module's global | `global x: int = 0;` after the last global, or before the first trigger |
| a bare reserved word as a declaration, assignment target or constant read (`let import: int = 1;`) | `"import"`, `variable("import")` or `const("import")` |
| a common mistake from another language (`if (y = 3)`, `x += 1`, `a and b`, `'text'`, `elif`, `while (c) { ... }`) | the exact rewrite listed in [language](language.md#api-diagnostics) |

The rewrite renders arguments from the syntax tree, so comments inside the call
are dropped. Advice that is not one edit (quote a protected declaration, declare a
constant at top level) has no fix.

## Built-in documentation

Hover, completion and signature help describe built-ins from the catalog: the
policy [description override](metadata.md#descriptions) when one exists,
otherwise the native description. Flat signatures name every parameter from
policy [parameter names](metadata.md#parameter-names)
(`H.Start(pc: card, partner: card)`, `Notification(text: string, isImportant: bool = false)`);
member signatures use their `[members]` argument names, and macros their
formal names. The server reads no documentation file.

F12 on a built-in returns `aa2m-builtin:/<anchor>.md` at line 0. The server
serves those pages itself through `workspace/textDocumentContent` (LSP 3.18),
rendered from the same entries `aa2modulus editor-data catalog` writes to
`builtins.json` ([development](development.md#checks)); an unknown anchor gets
an "Unknown built-in" page. `workspace/symbol` lists built-ins ranked by name,
alias, native name and description (at most 200), each located at its page, so
a client finds built-ins by filtering results to the `aa2m-builtin` scheme.
The pages are built on the first page or symbol request, which compiles every
example once. Anchors are
stable across renames: expression anchors include the return type, constant
anchors the original scoped ordinal (`action-108`, `expression-int-101`,
`named-constant-int-310`), and aliases and literal source values share their
row's anchor. Pages, built-in symbols and built-in definition targets exist
only when the client advertises `workspace.textDocumentContent`.
Authored definitions continue to navigate to their source.

Binding, formatting and editor features use
that catalog's source forms and exact signature candidates. Equivalent constant
rows produce one completion; qualified literal values insert a name that binds
to a primitive literal, and hover/F12 retain the original native row's anchor.

## Module commands

The server advertises `aa2modulus.prepareCompile`, `aa2modulus.compileDocument` and
`aa2modulus.decompileModule` through `workspace/executeCommand`; request and result
shapes are in the [client contract](#command-wire-format).
Compilation reads saved disk inputs, checks relevant buffers and disk files for
changes (stale or dirty inputs report `ContentModified`), rejects source/import
destinations, and atomically commits output only after strict compilation succeeds;
canceled or failed requests preserve existing output. Decompilation returns
readable source with raw fallbacks and recovery diagnostics, including semantic
errors and trailing-byte warnings; fatal read/decode failures are request errors.
Command diagnostic messages use the CLI `short` form (`file:line:col:
severity[CODE]: message`); published and command diagnostics append a finding's
notes and help as `note: ...` and `help: ...` lines. Command diagnostics also
carry the `code`, the headline-free `detail`, and, when the finding's text is
known, a `range` in the negotiated position encoding: compile findings name the
module or import `uri` (`target: "source"`), and decompile findings point into
the returned source (`target: "recovered"`). Output, read and binary-only
findings have no range.

Protocol behavior follows [LSP 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)
and uses [Pygls lifecycle and synchronization](https://pygls.readthedocs.io/en/latest/servers/reference/built-in-features.html).

## Client contract

These are the server-side facts a client relies on. Client behavior (settings,
trust, UI) belongs to the client.

- **Launch and transport:** run `aa2modulus lsp-server` (or
  `python -m aa2modulus lsp-server`); JSON-RPC runs over the process's standard
  input and output. There is no `--stdio` flag.
- **Documents:** language IDs `aa2m` and `aa2mi`, with `file:` or `untitled:`
  URIs. Command file arguments are local `file:` URIs on the server's host.
- **Initialize result:** `serverInfo` carries `name` and `version`.
  `capabilities.experimental.aa2modulus` is
  `{ "contractVersion": 1, "builtinCatalog": true }`. A client gates features
  on these fields, not on `serverInfo.version`.
  `contractVersion` increments only on a breaking wire change. An additive
  feature adds a flag instead, which is present and `true` only when the
  feature is available; a missing flag means unsupported. `builtinCatalog`
  means built-in pages, symbols and definition targets (see
  [built-in documentation](#built-in-documentation)); it and
  `capabilities.workspace.textDocumentContent.schemes: ["aa2m-builtin"]` appear
  only when the client advertises `workspace.textDocumentContent`. A client
  that serves its own `aa2m-builtin` documents must stop doing so for this
  contract. `syntax` is always present:
  `{ "version": <policy language_version>, "fingerprint": "<64 hex>" }`. The
  fingerprint is the SHA-256 of the grammar's lexicon, the same value
  `aa2modulus editor-data lexicon` prints; built-ins and policy do not change
  it. A client whose highlighting grammar records another fingerprint should
  warn, not refuse.
- **Release manifest:** each release publishes `aa2modulus-manifest.json`
  beside its zips, so a client can judge a release before it downloads one:
  `{ "schema": "aa2modulus.release-manifest.v1", "version", "contractVersion",
  "syntax", "features": { "builtinCatalog": true }, "platforms": [...] }`.
  `version` equals `serverInfo.version`; `contractVersion` and `syntax` equal
  the initialize result's. `features` lists every flag the server can offer;
  a client receives each one in initialize only when it supports the feature.
  `platforms` names the targets that built (`linux-x64`, `windows-x64`). The
  binary prints its part with `aa2modulus editor-data manifest`.
- **Commands:** `executeCommandProvider.commands` lists the module commands.
  A client checks the list before it starts a command.
- **Diagnostics:** published with the document version when known. A closed
  file keeps its diagnostics (published without a version, rechecked from disk)
  until it is reopened or deleted; an untitled document clears on close.
  `Diagnostic.data` is opaque: a client only echoes it back in
  `textDocument/codeAction` context and never reads or stores it.

### Command wire format

Each command takes one object in `workspace/executeCommand` `arguments`.
Document versions are integers; booleans are rejected.

| Command | Request object | Result object |
| --- | --- | --- |
| `aa2modulus.prepareCompile` | `{ "textDocument": { "uri", "version" } }` | `{ "dependencies": string[], "diagnostics": CommandDiagnostic[] }` |
| `aa2modulus.compileDocument` | `{ "textDocument": { "uri", "version" }, "outputUri": string }` | `{ "compiled": boolean, "diagnostics": CommandDiagnostic[] }` |
| `aa2modulus.decompileModule` | `{ "inputUri": string }` | `{ "source": string, "diagnostics": CommandDiagnostic[] }` |

`prepareCompile` needs an open `.aa2m` module at the given version. It returns
the import URIs reachable from the current buffers (unsaved libraries
included), so the client can save them before it calls `compileDocument`.
These URIs are source imports, not `depends_on` names. Request failures,
invalid parameters and changed inputs are JSON-RPC/LSP errors.

A `CommandDiagnostic` always has `severity` (`error`, `warning` or `info`) and
`message`: the CLI short line followed by any `note:`/`help:` lines. Other
fields are optional:

| Field | Type | Meaning |
| --- | --- | --- |
| `code` | string | Diagnostic code, for example `WRITE_ERROR` |
| `detail` | string | `message` without the location headline |
| `target` | `"source"` or `"recovered"` | What `range` points into; present only with `range` |
| `uri` | string | Source document for `target: "source"` |
| `range` | LSP `Range` | Location in the negotiated position encoding |
| `related` | `{ uri?, range, message }[]` | Located notes; no `uri` inside recovered source |

Compile findings use `target: "source"` with a `uri`; decompile findings point
into the returned `source` with `target: "recovered"`. Output, read and
binary-only findings (such as trailing bytes) have no `range`. A client ignores
a `range` whose `target` it does not know.

### CLI short format

`--diagnostic-format short` prints one line per finding, which editor problem
matchers parse:

```text
<file>:<line>:<column>: <error|warning|info>[<CODE>]: <message>
```

`file` is the path as given on the command line. `line` and `column` start at
1, and `CODE` matches `[A-Z0-9_]+`. Binary-only findings print
`<file>@0x<OFFSET>: ...` instead, and related notes print
`<file>:<line>:<column>: note: ...`.
