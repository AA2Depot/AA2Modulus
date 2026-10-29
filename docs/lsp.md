# Language server

The shared CLI includes a language server for `.aa2m` modules and `.aa2mi`
libraries. It provides diagnostics, completion, hover, signature help,
go-to-definition, import links, document and workspace symbols, references,
occurrence highlights, rename, semantic highlighting, parameter-name inlay
hints and quick fixes.

You can use an editor's existing LSP client or the VS Code extension. The
extension lives in its own repository ([`aa2modulus-vscode`](https://github.com/AA2Depot/aa2modulus-vscode)) and owns its own
setup and troubleshooting. The [client contract](#client-contract) lists the
wire facts any client relies on.

## Launch

Prepare the environment using [development setup](https://github.com/AA2Depot/AA2Modulus/blob/main/README.md#development),
then configure the client to run:

```bash
python -m aa2modulus lsp-server
```

Run it from this checkout with its managed interpreter. For example, the launch
settings an LSP client needs are:

```json
{
  "command": "/path/to/aa2modulus/.venv/bin/python",
  "args": ["-m", "aa2modulus", "lsp-server"],
  "cwd": "/path/to/aa2modulus"
}
```

For a [standalone executable](standalone.md), use its absolute path with the
arguments `["lsp-server"]`. It can run from any working directory:

```json
{
  "command": "/path/to/aa2modulus",
  "args": ["lsp-server"]
}
```

On Windows, use `aa2modulus.exe`, or `.venv/Scripts/python.exe` for source-tree
launches. If the client requires a different working directory, put the
checkout on its `PYTHONPATH`.

Register `.aa2m` files with language ID `aa2m`. Saved `.aa2mi` libraries can use
`aa2m` or `aa2mi`, and the starter uses `aa2mi` for saved and untitled
libraries. An untitled library must use language ID `aa2mi`.

The client owns the process and connects through stdin/stdout. Log messages go
to stderr. `lsp-server --help` and `lsp-server --version` exit without opening a
session. `--version` prints the `serverInfo.version` sent at `initialize`
([version](development.md#version)). There are no transport flags. The
[standalone guide](standalone.md) records tested platforms and build recipes.

## Authoring behavior

- Diagnostics use the same strict compiler checks, including imported errors
  and macro and template origins. A file with syntax errors shows each
  independent one (up to 25). It shows no binding errors until the syntax is
  clean. A shared library error appears once and keeps the related locations
  from each open root.
- Unsaved library buffers take precedence over disk. Edits and closes refresh
  dependent open roots. The server checks observed disk imports every second.
  Missing libraries stay observed, so creating one can refresh diagnostics.
- A closed `file:` document keeps its diagnostics. The server re-checks it from
  disk (reusing the last result when the buffer matched disk) and follows disk
  changes until the file is reopened, deleted or unreadable. Untitled and
  unsaved-new files clear on close. Files never opened get no diagnostics. Only
  references and rename read them ([below](#references-and-rename)). Closed
  files get no hover, completion or other authoring results.
- Hover and definition use the binder's selected declarations and metadata.
  Built-ins show signatures, descriptions and policy defaults. Definitions
  navigate to authored variables, macro parameters and calls, template slots
  and uses, and import targets. Generated template-local names stay out of the
  outline.
- `textDocument/documentLink` returns one link per import path token whose file
  was read, targeting that file. It agrees with definition on the path.
  Unresolved paths get no link, and neither do imports in untitled documents.
- Completion and signature help use the existing grammar for incomplete
  prefixes. They respect comments, strings and nested calls, and they replace
  exact name tokens. A separate bounded editor view recovers completed
  declarations and successful binder selections around unfinished statements
  and imported files. It permits 32 syntax faults plus the ordinary source and
  import budgets. In a module file, a top-level trigger is read as a trigger
  of the module, so a stray `}` that closes the module early does not cost
  the triggers after it their names. Strict diagnostics and compilation still
  use the original input. The editor view never reuses locations from an
  earlier buffer.
  Suggestions respect statement, value and event context, declaration scope and
  known expected types, and they keep distinct overloads.
- Conditions and boolean value slots also offer operands for comparisons before
  the comparison operator is typed. For example, `if (Globals.` offers
  `Globals.CurrentDay`, and you complete the condition with `== 1` or another
  comparison. Direct `!` operands remain boolean. Known comparison and argument
  types narrow the candidates. Unknown complex operand types stay unrestricted.
  Literal-only global initializers and declaration name and type slots use
  their own grammar states.
- Namespace roots (`Globals.`, `Context.`) match case-sensitively. Card-first
  built-ins are members only, and the server never offers them as flat names.
  After a receiver, completion offers the configured members. A receiver can be:
  - a variable (`coach.`);
  - `variable("x").`;
  - `(expr).`;
  - a call result;
  - a member chain (`coach.Target.`);
  - a bare zero-argument `int` built-in (`ThisCard.`, `TriggeringCard.`).

  Statement position lists action members. Value positions list value members
  of the expected type. Properties (zero-argument values) insert without
  parentheses, and calls insert the usual snippet. Only the member text is
  replaced. `Context.` still lists the `Context.*` built-ins. Signature help on
  any receiver lists the explicit arguments only. Hover and definition on a
  member or property name show `<card>.AddLike(towards: card, amount: int)` or
  `<card>.Target -> card` with the native description, and they open the
  built-in page.
- [Card](language-contract.md#cards) values show their type. Variables show
  `coach: card`. Card-valued built-ins (`ThisCard`, `Context.NpcTalkTarget`,
  `coach.Target`) show `Returns: card` in hover and completion documentation.
  Flat card slots show `Globals.IsSeatFilled(seat: card)`. At the start of an
  argument that expects a card (`coach.AddLike(`, `Globals.IsSeatFilled(`, a
  `card` macro formal), card-valued built-ins and `card` variables sort first.
  Every other item keeps its order after them. Other positions are not ranked.
  Nothing is filtered by role, so an `int` there stays offered (it needs
  `Card(...)`).
- Inside `@allow(`, completion offers the policy's acknowledgeable hazard codes
  (kind EnumMember) that the attribute does not list yet. No quick fix adds an
  `@allow`, because bypassing a hazard is not recommended.
- For clients with `snippetSupport`, keyword completion adds Snippet items
  (tab-indented bodies) where the grammar accepts their keyword:
  - top level: `module`, `import`, `macro`, `const` declarations and library
    `trigger` templates;
  - in a module: `trigger`, `import.trigger`, `global`, `const`, `description`
    and `depends_on`;
  - in templates and instances: `slot`. In macros: `param`. In triggers: `on`
    and `let`;
  - as statements: `if`, `if`/`else`, `loop` and `for`. In a trigger, `for`
    declares its `let` counter directly. In macros it declares none;
  - after an `if` block: `else` and `else if`.

  Raw forms get no snippets. A document holding only whitespace and comments
  ranks a starter first: a module with a trigger for `aa2m`, and a macro plus
  trigger template for `aa2mi`. Keywords and snippets follow the source kind
  (language ID or `.aa2mi`). A library is never offered `module`, and a module
  file is never offered a top-level `trigger` or a second `module`.
- Compile-time constants (`const`) complete in value positions with kind
  Constant and detail `const Name: type = value` (the resolved literal). The
  expected type filters them, as it does for variables. Module constants are
  visible only in the module. Top-level and imported-library constants are also
  visible in macro bodies and trigger templates. A name that is not an
  identifier inserts `const("Name")`. Inside `const("`, every visible constant
  name is offered, and the typed text (through the closing quote) is replaced by
  the escaped name. Hover on a use or declaration shows
  `const Name: type = value`. Definition jumps to the declaration name from any
  use: bare, `const("X")`, global initializer, constant-to-constant link or
  imported library constant. Document symbols list top-level constants and
  module constants (as module children) with kind Constant.
- Zero-argument runtime expressions use property items and insert bare names.
  Events use event items after `on`. In statement positions, variable
  assignment targets appear alongside actions and macros. So do card receivers
  (card-valued built-ins, card variables and card formals), which the server
  inserts without `;` so a member can follow. Value slots of any type offer
  card receivers too, ranked after the values that match, because a card member
  can return every value type.
- Qualified edits replace the complete token and preserve existing calls and
  terminators. They keep the full candidate filter text, so a client can refine
  the original list as more characters are typed. Known calls with no remaining
  usable arguments suppress impossible value suggestions.
- Quoted, keyword or dotted authored variable names insert an explicit
  `variable("name")` reference so they bind to the declaration. A getter
  shadowed by an authored variable inserts an explicit empty call. This never
  applies to the protected `ThisCard` and `TriggeringCard`, which variables
  cannot shadow. When completing an existing call's callee, variable and
  constant values are excluded.
- A first authoring request waits for an existing in-flight analysis instead of
  scheduling duplicate analysis of the same buffer. New edits and import changes
  still invalidate results. A second request is unnecessary to obtain
  completion.
- Clients advertising snippet support receive placeholders for required
  arguments. Arguments with policy defaults are omitted. Existing call
  parentheses and arguments are preserved. The VS Code client opens parameter
  help after accepting a call.
- Adjacent leading `//` and `/* ... */` comments document authored declarations
  in hover and completion, including imported buffers. A blank line or
  intervening code ends the association. Comments remain absent from serialized
  modules.
- Position encoding defaults to UTF-16. Clients can negotiate UTF-8 or UTF-32.
  Source spans keep their inclusive Unicode code-point contract internally.

The server uses bundled metadata and policy and the existing source budgets. It
does not read binary modules, so a variable the module never declares is
undefined until declared. Formatting is not planned (revisit if users ask).

## References and rename

References (`textDocument/references`), occurrence highlights
(`textDocument/documentHighlight`) and rename (`textDocument/prepareRename`,
`textDocument/rename`) work on authored declarations: globals, `let` locals,
constants, macros, macro parameters, trigger templates and template slots.

A declaration's occurrences are its name plus every use the binder selected for
it:

- bare names, `variable("…")` and `const("…")`;
- assignment and `for` targets;
- macro calls in any case;
- `import.trigger` template names;
- `slot` bindings at instantiation sites.

Strings, comments, built-ins, module and trigger names and card-storage keys
are never occurrences. While a file has errors, these features use the editor
view's selections, as hover does.

- Scope. Imports accept only `.aa2mi` paths, so the server searches a
  declaration in any other file in that file alone. It searches a declaration
  in a saved library across the workspace. On the first such request, the
  server reads every `.aa2m` and `.aa2mi` file under the workspace folders
  (including folders added later). It skips hidden files and directories and
  stops at 2,000 files, with a warning when it reaches the cap. Closed files
  are read from disk, and open buffers override their imports. The server
  caches their analyses and reuses them only while the file and every input it
  read are unchanged. A client that supports dynamic
  `workspace/didChangeWatchedFiles` registration receives a
  `**/*.{aa2m,aa2mi}` watcher, and created or deleted files trigger
  rediscovery. Other clients are rediscovered on every such request. A request
  with a `workDoneToken` reports `$/progress` while uncached files are read.
  Without a workspace folder, the server searches open documents and their
  imports.
- Workspace symbols. `workspace/symbol` searches the same sources. It lists
  top-level constants, macros, templates and modules, and each module's
  globals, constants and triggers (`containerName` is the module name). It does
  not list locals, macro parameters or slots. Names match without case: exact
  first, then prefix, then substring, each ordered by file and position. These
  results precede any built-ins, and the list holds at most 200.
- Highlights. They cover the current document. Declarations, assignment targets
  and `for` targets are writes. Other uses are reads.
- Spelling. A new name that is a non-keyword, unprotected identifier is written
  bare. Otherwise, declarations and `for` targets are quoted
  (`let "my count": int = 0;`), variable uses become `variable("…")` and
  constant uses become `const("…")`. Quoted sites stay quoted. Macro and slot
  names must be identifiers, and `ThisCard` and `TriggeringCard` are refused.
- Validation. The server applies the edits in memory and re-analyzes every
  affected module and library. It refuses the rename and names the conflicting
  location in any of these cases:
  - a renamed use would refer to another declaration or a built-in (shadowing);
  - another use would start referring to the renamed declaration;
  - the edit introduces an error.

  A file that changed during the request returns `ContentModified`.
- Output. Renaming a macro, constant, parameter or slot leaves compiled output
  byte-identical. Renaming a template also writes the old name as the output
  name of each `import.trigger` that had none, so trigger names are kept.
  Renaming a global or local changes the serialized variable name. For a
  global, the server also shows a warning saying so.

Edits use versioned `documentChanges` when the client supports them (closed
files have no version), and `changes` otherwise.

## Semantic highlighting

`textDocument/semanticTokens/full` colors a name by what the binder selected for
it, regardless of how it is spelled. The legend uses standard token types, so
themes color it without configuration:

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

A lexical scan of the text colors the rest, so a file with syntax errors is
colored too:

| Text | Token type |
| --- | --- |
| keywords and raw forms (`module`, `import.trigger`, `raw_action`, `constant`, `variable`), `true`, `false`, `float_bits`, `invalid` after `default`, `current` or `constant` | `keyword` |
| types and `Card` (`int`, `card`, `type`, `invalid` elsewhere) | `type` |
| operators and `=` (a sign before a number included) | `operator` |
| `@allow` | `decorator` |
| codes inside `@allow( … )` | `enumMember` |
| integers, floats, hex digits | `number` |
| strings, module and trigger names | `string` |
| `//` and `/* */` comments, one token per line | `comment` |

Lexical tokens have no modifiers. A name token wins over an overlapping lexical
token. Quoted names (`variable("coach")`, `const("Tag")`, `param "text"`) are
one name token over the quoted string. Other punctuation and unresolved names
get no token. A typo stays uncolored while its diagnostic reports it.

While a file has errors, the editor view's selections are used, as for hover. A
request waits for the analysis of the current text, so tokens never come from an
older version. When an import changes under an unchanged document, the server
sends `workspace/semanticTokens/refresh` once, if the client supports it. Range
and delta requests are not offered.

## Inlay hints

`textDocument/inlayHint` labels literal arguments with their parameter names
(`Notification("x", isImportant: true)`). The hints are `Parameter` hints with
right padding. Literals are numbers, bools, strings, `float_bits(...)` and a
literal under `!`. The server never labels computed arguments.

Names come from what the binder selected for the call:

- a member form's explicit arguments (the receiver is never labeled);
- the policy `[parameter_names]` of the chosen flat overload;
- a macro's parameters.

No hint is shown when:

- the call has one parameter named `value` or contained in the callee name
  (`coach.SetStyle(2)`, `ThisCard.SetVirtue(3)`, `ToInt("1")`);
- a string literal fills a storage key (member role `key`, or a flat parameter
  named `key`): `ThisCard.GetBool("Tutor", fallback: true)`;
- the call is unresolved or raw.

While a file has errors, the editor view's selections are used. Clients toggle
hints with their own setting (VS Code: `editor.inlayHints.enabled`). The server
has no setting for it.

## Quick fixes

Some diagnostics carry concrete edits behind their `help` line. The server
publishes them in the diagnostic's private `data` with the document version.
`textDocument/codeAction` (kind `quickfix`) turns the echoed data into edits
without re-analysis. The server offers no fix for an older version. A
diagnostic with exactly one fix marks it preferred.

| Finding | Fix |
| --- | --- |
| flat card-first call (`SetVirtue(ThisCard, 3);`) | `ThisCard.SetVirtue(3);` (one per matching member form) |
| wrong-case namespace root (`context.npctalktarget`) | the whole canonical name `Context.NpcTalkTarget`. When the tail is already exact, unknown or ambiguous, only the root changes (`globals.CurrentDay` to `Globals`) |
| assignment to a protected name (`ThisCard = 3;`) | `variable("ThisCard") = 3;` |
| `AMBIGUOUS_CONST` read | `const("K")` or `variable("K")`. An assignment target gets only `variable("K")` |
| an `int` where a card is expected (`n.SetVirtue(1)`, `coach == n`) | `Card(n)` |
| `UNDEFINED_VARIABLE` with a known type, such as a decompiled read of a variable the module never declares | `global x: int = 0;` after the last global, or before the first trigger |
| a bare reserved word as a declaration, assignment target or constant read (`let import: int = 1;`) | `"import"`, `variable("import")` or `const("import")` |
| a common mistake from another language (`if (y = 3)`, `x += 1`, `a and b`, `'text'`, `elif`, `while (c) { ... }`) | the exact rewrite listed in [language](language-contract.md#api-diagnostics) |

The rewrite renders arguments from the syntax tree, so comments inside the call
are dropped. Advice that takes more than one edit has no fix. Two examples are
quoting a protected declaration and declaring a constant at top level.

## Built-in documentation

Hover, completion and signature help describe built-ins from the catalog. They
use the policy [description override](metadata.md#descriptions) when one
exists, and the native description otherwise. Flat signatures name every
parameter from policy [parameter names](metadata.md#parameter-names)
(`H.Start(pc: card, partner: card)`, `Notification(text: string, isImportant: bool = false)`).
Member signatures use their `[members]` argument names, and macros use their
formal names. The server reads no documentation file.

F12 on a built-in returns `aa2m-builtin:/<anchor>.md` at line 0. The server
serves those pages itself through `workspace/textDocumentContent` (LSP 3.18).
It renders them from the same entries `aa2modulus editor-data catalog` prints
([development](development.md#checks)). An unknown anchor gets
an "Unknown built-in" page.

`workspace/symbol` lists built-ins ranked by name, alias, native name and
description (at most 200). Each is located at its page, so a client finds
built-ins by filtering results to the `aa2m-builtin` scheme. Authored results
come first and use `file:` or `untitled:`.

The server builds the pages on the first page or symbol request, which compiles
every example once. Anchors are stable across renames. Expression anchors
include the return type, and constant anchors include the original scoped
ordinal (`action-108`, `expression-int-101`, `named-constant-int-310`). Aliases
and literal source values share their row's anchor. Pages, built-in symbols and
built-in definition targets exist only when the client advertises
`workspace.textDocumentContent`. Authored definitions continue to navigate to
their source.

Binding, formatting and editor features use that catalog's source forms and
exact signature candidates. Equivalent constant rows produce one completion.
Qualified literal values insert a name that binds to a primitive literal, and
hover and F12 keep the original native row's anchor.

## Module commands

The server advertises `aa2modulus.compileDocument` and
`aa2modulus.decompileModule` through `workspace/executeCommand`. Request and
result shapes are in the [client contract](#command-wire-format).

Compilation uses the same inputs as analysis: the synced text of each open
document in the import graph, saved or not, and disk for the rest. The client
does not need to save first. Before it commits, the server checks three things:
no used buffer changed or closed, no buffer opened for a file read from disk,
and no disk input changed. Otherwise it reports `ContentModified`. It rejects
source and import destinations. It commits output atomically and only after
strict compilation succeeds, so canceled or failed requests preserve existing
output.

Decompilation writes readable source to a new file beside the binary. The
source has raw fallbacks and recovery diagnostics, including semantic errors
and trailing-byte warnings. Fatal read, decode and write failures are request
errors.

Command findings reach the client three ways:

- The server publishes located findings with `textDocument/publishDiagnostics`,
  in the negotiated position encoding. They go on the module or import
  (compile) or the written file (decompile). A finding that repeats an analysis
  diagnostic on the same URI (same range, severity, code and message) is
  hidden, so compile mostly adds writer errors. The next completed compile of
  the same root replaces its findings. An edit or close of a file, or a watched
  change or delete, drops the command findings on it.
- The server logs every finding once with `window/logMessage`. The message
  starts with `compile: ` or `decompile: `, then the CLI `short` line
  (`file:line:col: severity[CODE]: message`) and any `note: ...` and
  `help: ...` lines.
- The result counts errors and warnings. It lists the findings without a range:
  output, write, read and binary-only findings.

Protocol behavior follows [LSP 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)
and uses [Pygls lifecycle and synchronization](https://pygls.readthedocs.io/en/latest/servers/reference/built-in-features.html).

## Client contract

These are the server-side facts a client relies on. Client behavior (settings,
trust, UI) belongs to the client.

- Launch and transport: run `aa2modulus lsp-server` (or
  `python -m aa2modulus lsp-server`). JSON-RPC runs over the process's standard
  input and output. There is no `--stdio` flag.
- Documents: language IDs are `aa2m` and `aa2mi`, with `file:` or `untitled:`
  URIs. Command file arguments are local `file:` URIs on the server's host.
- Initialize result: `serverInfo` carries `name` and `version`.
  `capabilities.experimental.aa2modulus` is
  `{ "contractVersion": 2, "builtinCatalog": true, "completionSnippets": true, "lexicalTokens": true }`.
  A client gates features on these fields, not on `serverInfo.version`.
  - `contractVersion` increments only on a breaking wire change. An additive
    feature adds a flag instead. A flag is present and `true` only when the
    feature is available, and a missing flag means unsupported.
  - `builtinCatalog` means built-in pages, symbols and definition targets (see
    [built-in documentation](#built-in-documentation)). It and
    `capabilities.workspace.textDocumentContent.schemes: ["aa2m-builtin"]`
    appear only when the client advertises `workspace.textDocumentContent`. The
    server owns the `aa2m-builtin` scheme, so a client must not serve its own
    documents under it.
  - `completionSnippets` means keyword snippets and the empty-document starters
    (see [authoring behavior](#authoring-behavior)). It appears only when the
    client advertises `completionItem.snippetSupport`.
  - `lexicalTokens` means semantic tokens also color keywords, types,
    operators, numbers, strings and comments (see
    [semantic highlighting](#semantic-highlighting)). It is always present.
  - `syntax` is always present:
    `{ "version": <policy language_version>, "fingerprint": "<64 hex>" }`. The
    fingerprint is the SHA-256 of the grammar's lexicon, the same value
    `aa2modulus editor-data lexicon` prints. Built-ins and policy do not change
    it. A client whose highlighting grammar records another fingerprint should
    warn and not refuse.
- Release manifest: each release publishes `aa2modulus-manifest.json` beside
  its zips, so a client can judge a release before it downloads one:
  `{ "schema": "aa2modulus.release-manifest.v1", "version", "contractVersion",
  "syntax", "features": { "builtinCatalog": true, "completionSnippets": true,
  "lexicalTokens": true },
  "platforms": [...] }`.
  - `version` equals `serverInfo.version`. `contractVersion` and `syntax` equal
    the initialize result's.
  - `features` lists every flag the server can offer. A client receives each
    one in initialize only when it supports the feature.
  - `platforms` names the targets that built (`linux-x64`, `windows-x64`).
  - The binary prints its part with `aa2modulus editor-data manifest`.
- Commands: `executeCommandProvider.commands` lists the module commands. A
  client checks the list before it starts a command.
- Command output: decompile creates `<input>.aa2m`, or `<input>-2.aa2m` up to
  `-100` when a name exists on disk or is open. It never overwrites. When the
  client advertises `window.showDocument.support`, the server opens the file
  with `window/showDocument` before it returns the result.
- Diagnostics: the server publishes them with the document version when known.
  Analysis uses the source `aa2modulus`. Command findings use
  `aa2modulus compile` and `aa2modulus decompile`. A closed file keeps its
  diagnostics (published without a version, rechecked from disk) until it is
  reopened or deleted. An untitled document clears on close.
  `Diagnostic.data` is opaque. A client only echoes it back in
  `textDocument/codeAction` context and never reads or stores it.

### Command wire format

Each command takes one object in `workspace/executeCommand` `arguments`.
Document versions are integers, and booleans are rejected.

| Command | Request object | Result object |
| --- | --- | --- |
| `aa2modulus.compileDocument` | `{ "textDocument": { "uri", "version" }, "outputUri": string }` | `{ "compiled": boolean, "outputUri"?: string, "errors": int, "warnings": int, "unlocated": CommandFinding[] }` |
| `aa2modulus.decompileModule` | `{ "inputUri": string }` | `{ "outputUri": string, "errors": int, "warnings": int, "unlocated": CommandFinding[] }` |

`compileDocument` needs an open, file-backed `.aa2m` module at the given
version. The file need not exist on disk yet. Contract version 2 removed
`prepareCompile`, which listed imports for the client to save, and the
`diagnostics` arrays of both results. Request failures, invalid parameters and
changed inputs are JSON-RPC/LSP errors.

Compile `outputUri` is present only when `compiled` is true. Decompile
`outputUri` is the file the server wrote. `errors` and `warnings` count every
finding of the command, located or not, including hidden duplicates. A
`CommandFinding` is `{ "severity", "code", "message" }`. `severity` is `error`,
`warning` or `info`, and `message` is the CLI short line followed by any
`note:` and `help:` lines.

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
