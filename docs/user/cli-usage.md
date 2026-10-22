# CLI usage

`aa2modulus` has five commands. Run `aa2modulus <command> --help` for the same
list in the terminal.

| Command | What it does |
| --- | --- |
| `validate SOURCE` | Check a `.aa2m` module or `.aa2mi` library. Writes nothing. |
| `compile SOURCE -o OUTPUT` | Compile a `.aa2m` module to an extensionless binary module. |
| `decompile MODULE [-o OUTPUT]` | Turn a binary module into `.aa2m` source (stdout without `-o`). |
| `inspect MODULE` | Print a binary module's records with their native labels and IDs. |
| `lsp-server` | Run the [language server](../lsp.md) over stdio for an editor. |

`aa2modulus --version` and `aa2modulus lsp-server --version` print the version.

## Output and exit codes

The main result (`valid: ...`, `compiled: ...`, recovered source) goes to
stdout. Diagnostics and the closing summary line go to stderr. `inspect`
prints its report, diagnostics included, to stdout.

| Exit code | Meaning |
| --- | --- |
| `0` | Success. Warnings may still be printed. |
| `1` | Input error: the source or module has an error, or a file could not be read or written. |
| `2` | Usage error: a missing or invalid argument, or an input file that does not exist. |
| `3` | Internal configuration error in the shipped language data. Report it as a bug. |

`compile` never creates or overwrites its output when it fails. `decompile`
returns `0` when it recovers source, even if that source has semantic errors.

## Diagnostic options

`validate`, `compile`, `decompile` and `inspect` accept:

| Option | Effect |
| --- | --- |
| `--diagnostic-format human` | Default. Headline, location, source snippet with carets, notes and help. |
| `--diagnostic-format short` | One `file:line:column: severity[CODE]: message` line per finding, for scripts and editor problem matchers. |
| `--color auto\|always\|never` | Default `auto`: color only a terminal, and never when `NO_COLOR` is set. |
| `--verbose` | Add binary offsets and structural paths as evidence. |

Each code is listed in the [diagnostic reference](../reference/diagnostics.md).

## Globals from other modules

A module can read a global that only another module on the card declares.
`decompile` keeps such a reference raw and warns, and its help names the
declaration to add, for example `global counter: int = 0;`. Until you add it,
`validate` and `compile` report the variable as an error. Declaring it is safe:
AAUnlimited keeps a card's existing value for a global it already has.

## Inspect options

| Option | Effect |
| --- | --- |
| `--validation-profile strict` | Default. Apply authoring rules. |
| `--validation-profile native` | Apply only the checks AAUnlimited itself makes when it loads a trigger. |
| `--strict` | Exit `1` on validation errors or trailing bytes. Without it, `inspect` reports and exits `0`. |

## Source limits

`validate` and `compile` stop with a `*_LIMIT` error when source exceeds a
limit. The defaults suit any real module; raise one only for an unusual input.
Every value is a nonnegative integer.

| Option | Limits | Default |
| --- | --- | ---: |
| `--max-source-chars` | characters in one file | 4,194,304 |
| `--max-total-source-chars` | characters across the file and its imports | 16,777,216 |
| `--max-source-nodes` | nodes in each parse, syntax-tree and bound stage | 200,000 |
| `--max-syntax-depth` | parse depth (at most 512) | 256 |
| `--max-source-nesting` | statement and expression nesting (at most 128) | 64 |
| `--max-syntax-errors` | syntax errors reported (at least 1) | 25 |
| `--max-binding-errors` | name and type errors reported (at least 1) | 100 |
| `--max-binding-work` | name and overload resolution work | 200,000 |
| `--max-macro-nodes` | nodes produced by macro expansion | 200,000 |
| `--max-macro-depth` | nested macro calls (at most 128) | 64 |
| `--max-import-files` | distinct imported libraries | 128 |
| `--max-import-depth` | import steps from the module to a library | 32 |
