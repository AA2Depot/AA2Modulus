# Code style

This guide covers new and edited code in `aa2modulus/`, `tools/` and `tests/`.
It writes down the conventions the code already follows.

Some rules are checked for you. `mise run lint` runs Ruff, strict mypy and
`tools/check_layers.py`, which cover formatting, lint rules, types and
layering. This guide is about the things those tools can't check.

When you edit a file that breaks one of these rules, fix the lines you touch
and leave the rest of the file alone unless the task needs it. If the guide
doesn't cover something, do what the surrounding code does.

## Modules and imports

- Start every module with a one-line docstring that says what the module owns.
  Add a paragraph only for contracts the code can't show on its own.
- After the docstring comes `from __future__ import annotations`, then the
  imports in Ruff's order. Ruff checks both the docstring and the future
  import.
- Inside `aa2modulus/`, use relative imports, like `from ..core.locations
  import SourceSpan`. Tests and tools import `aa2modulus.…` absolutely.
- Import each name from the module that defines it, not through a package. A
  package's `__init__.py` holds nothing but its docstring, and no module
  declares `__all__`.
- A leading `_` marks a name as private to its module. The layer check rejects
  imports of another module's `_` names.
- Keep all imports at module level. There are two exceptions: the CLI imports
  `lsp.server` lazily (the layer check allows this one), and Windows-only
  standard modules (`ctypes`, `msvcrt`) are imported after a platform check.
- Once a module grows past about 600 lines, split it by responsibility. The
  layer check reports modules larger than that.

## Naming

- Use full words. The only abbreviations are established terms: `ast`, `hir`,
  `sir`, `lsp`, `uri` and `span`.
- A function that computes a value is named after the value: `builtin_call`,
  `texts_in_scope`, `declaration_span`. A function that does or checks
  something gets a verb: `bind_expression`, `lower_expression`, `check_type`,
  `record_reference`, `raise_error`.
- Stage types carry their stage in the name: `Source…` for AST nodes and
  `Bound…` for HIR nodes. SIR records keep their native names.
- Diagnostic codes are `UPPER_SNAKE_CASE` and say what went wrong, as in
  `UNDEFINED_VARIABLE` or `TEMPLATE_CAPTURE`. They are stable, so don't rename
  one once it exists.

## Types

- Annotate every function in `aa2modulus/` and `tools/`. Tests have their own
  rule, described under [Tests](#tests).
- Write `X | None` instead of `Optional`, and PEP 695 generics
  (`def f[T](…)`) instead of `TypeVar`.
- Parameters accept the widest protocol the function needs, such as
  `Iterable`, `Sequence` or `Mapping`. Collections you store or return are
  concrete, and immutable values use `tuple` and `frozenset`.
- Configuration parameters go after `*`, so callers have to pass them by
  keyword. That covers metadata, options, environment, encoding and cached
  analyses. An optional operand of the call, such as an expected type or a
  scope, can stay positional.
- `Any` is only for untyped JSON, TOML or wire data, and that data gets
  converted into typed records at the boundary. Use `cast` only when the code
  has already proved a narrowing that mypy can't follow.
- `assert` is only for narrowing a type that an earlier check already
  guarantees, such as `assert span is not None`. Never use it to validate
  input.

## Data

- Value types are `@dataclass(frozen=True, slots=True)`. Use plain
  `@dataclass(slots=True)` only for builders and for pass state that has to
  change.
- `__post_init__` has two jobs. It turns collection fields into tuples with
  `object.__setattr__`, and it enforces value invariants such as ranges,
  non-empty values and one-of rules. When an invariant fails, it raises
  `ValueError` with a lowercase message.
- Runtime type checks (`isinstance`, raising `TypeError`) belong only where raw
  data becomes typed: the binary reader, `from_ir` and the scalar fields it
  fills, the registry loader, the policy reader, LSP protocol conversion, Lark
  parse trees and command-line limits. Anything built from typed values, such
  as the Source AST and SIR child records, already has its types proved by
  strict mypy.
- Each stage has one model: Source AST, Bound HIR and SIR. Add a parallel
  representation only when it fills a concrete gap.

## Functions and control flow

- To dispatch on node types, write an `isinstance` chain with one branch per
  node type, each returning early. End the chain with an error for
  unsupported nodes.
- Return early rather than nesting. Format text with f-strings, and quote
  names in messages with `!r`.
- Module-level state is always a constant. If a shared object is built
  lazily, guard it with a lock, as `syntax/parser/engine.py` does.

## Errors and diagnostics

- Report authoring and native findings as `Diagnostic` values. Each one has a
  code and `help`, plus `fixes` when the edit is exact. Don't raise them as
  exceptions through the public interfaces.
- Each area has its own exception class, such as `SourceBindingError` or
  `RenameError`. It carries the diagnostics or the message the user sees.
- Messages in diagnostics and exceptions are lowercase and have no final
  period: `undefined variable 'x'`. Text that an editor shows the user as a
  sentence, such as an LSP refusal, starts with a capital letter.
- Catch `Exception` only at an LSP request boundary, and add a comment that
  explains why that request must not fail.

## Docstrings and comments

- A public function or class gets a docstring when its name and signature
  don't already make its behaviour, result or limits clear. Private helpers
  follow the same test.
- The first line is a summary phrase or sentence. Write code in
  ``double backticks``. In a multi-line docstring, put the closing quotes on
  their own line, and leave one blank line after a function docstring.
- Comments should be rare. Write one only to explain a reason the code can't
  show, such as a native quirk, an ordering constraint or a tool limitation.
  Don't narrate what the code does.
- Never write the language version number into code, tests or docs. Read
  `language_version` from `aa2modulus/language/policy.toml` instead.

## Tests

- Tests are plain `test_…` functions, not classes, and live in the directory
  for their area: `source`, `binary`, `metadata`, `cli` or `lsp`. Shared
  helpers live in `tests/support/`. A helper that only one module uses is a
  private `_` function in that module. Never import from another test module.
- Each test module starts with a docstring that says what behaviour it
  protects. Name each test after that behaviour, written as a phrase, like
  `test_nested_calls_report_all_arguments`.
- Assert on results you can observe (see
  [what the suite protects](development.md#what-the-suite-protects)): exact
  codes, spans, bytes and text. Don't assert only that a result is truthy or
  not `None`, accept one of several outcomes, or inspect private names,
  caches or internal records.
- Write expected values by hand. Never compute them with the code under test,
  or with the registry, policy or catalog that code reads.
- Each behaviour has one owner test, at the lowest layer that shows it.
  Before you add a test, search `tests/` for its diagnostic code, built-in or
  fixture. A test at a higher layer checks only that layer's own work, such
  as exit codes, rendering or the wire format.
- Test in-process: the app functions, the CLI through `main(argv)` with
  `capsys`, and LSP features through `SourceWorkspace` or the shared `client`
  fixture. Start a process only for what needs one: interpreter startup,
  stream encoding, import isolation, runtime independence, and LSP wire
  behaviour such as capabilities, notification order, server requests and
  cancellation.
- Use the session `context` and `metadata` fixtures. For a variant, use
  `dataclasses.replace(context, ...)`.
- Use `pytest.mark.parametrize` for tables of cases. Add a row only when it
  reaches a different branch, vary one thing at a time, and give each table
  to one test.
- Keep tests independent: never change parametrize values or shared state,
  and write files only under `tmp_path`. The suite runs in parallel, one file
  per worker.
- A test that takes more than 1 s says why in its docstring. Check new tests
  with `mise run test <file> --durations=5`.
- Test functions don't need annotations. Helpers can have them.

## Tools

- Each script in `tools/` does one job. It puts the repository root on
  `sys.path` before importing `aa2modulus`, and keeps its components in its
  own package under `tools/`.
- Scripts parse their arguments with `argparse`. If a script writes files,
  give it a `--check` option that compares without writing, where that makes
  sense.
