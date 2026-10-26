# Agent guidance

## The project

`aa2modulus` is an unreleased, cross-platform Python toolchain for AAUnlimited
trigger modules. Its source language is the unified `.aa2m`. Architecture and
language choices can change when that serves the task better. When you change
one, update the affected contracts, examples and acceptance tests in the same
task.

## Where the truth lives

The project itself is the source of truth: the code, the tests and the
documentation under `docs/` and in `README.md`. When they disagree, code and
focused tests win. If a live document is wrong, fix it.

Everything written by and for AI agents lives in `agent_data/`. This includes the
roadmap, the work log, plans with their handover notes, and the archive of
finished plans. Use it to learn what earlier agents did, why they did it and
where they stopped. It is orientation, not authority. Never treat a record there
as a specification or as a backlog. Check its claims against the code before
you rely on them.

`agent_data/` is ignored by git, so it can be missing from a fresh checkout. If
it is missing, create it with the layout below. Start with an empty work log, a
short roadmap that describes the current state you can confirm from the code,
and the plan template. Do not put agent records anywhere else in the
repository.

```
agent_data/
  README.md          what this directory is and how to use it
  ROADMAP.md         the single status page: current state, known limits, candidate work
  WORK_LOG.md        one entry per task, append-only
  plans/
    README.md        how plans work
    TEMPLATE.md      the template for a new plan
    active/          plans in progress, indexed by active/README.md
  archive/
    README.md        index of finished plans, newest first
    <year>/          finished, cancelled or superseded plans
```

The AAUnlimited source is not part of the workspace. The binary format and
runtime facts the project relies on are recorded in
[native format](docs/native-format.md), the generated registry and the native
fixtures. Use those, and never guess undocumented fields. Only registry
regeneration reads the source: `--source-root` must point to an existing
directory that holds a clean checkout at the pinned revision. Never modify that
checkout, require it at runtime, or copy it into artifacts.

## Starting a task

1. Run `git status --short` and diff the files you plan to edit. Keep unrelated
   edits, deletions and untracked files as they are. Never restore or clean up
   work you do not recognise.
2. Read `agent_data/ROADMAP.md` for the current state, known limits and
   candidate work. Then read `agent_data/plans/active/README.md`. If a plan
   matches your task, start with its Handover section.
3. Read only the latest one or two entries of `agent_data/WORK_LOG.md`, for
   example with `tail -n 80 agent_data/WORK_LOG.md`. The log is large; never
   read it whole.
4. Read only the live documents your task touches:
   - [README](README.md): setup and navigation.
   - [Grammar](docs/grammar.md) and [language reference](docs/language.md): the source contract.
   - [Metadata](docs/metadata.md): registries and the editable language policy.
   - [Native format](docs/native-format.md): binary layout and runtime evidence.
   - [Architecture](docs/architecture.md): which code owns which rule.
   - [Development](docs/development.md): `mise` tasks, checks and developer tools.
   - [Language server](docs/lsp.md): launch, authoring behaviour and limits.
   - [Code style](docs/style.md): conventions for all Python code you write
     or edit.
5. When you need the reason behind an earlier decision, search
   `agent_data/archive/` and the work log with `grep`, or use `git log`. Never
   read the archive wholesale.

## Design boundaries

- The core path is source text, then Source AST, Bound HIR, Serialized IR (SIR),
  validation and the binary writer. Build on these models and the shared
  diagnostics. Add a parallel representation only for a concrete gap.
- Preserve confirmed binary field order, widths, IDs, nested GUI trees and
  lossless recovery. Native fixture byte identity and the evidence in
  [native format](docs/native-format.md) are the proof.
- Readable and raw forms belong to one language. There is no legacy parser or
  alternate dialect. A requested redesign updates the grammar, parser,
  formatter, reference, examples and tests together.
- Generated facts live in `aa2modulus/metadata/registry/`, and language choices
  live in `aa2modulus/language/policy.toml`. Regenerate facts with
  `tools/generate_registry.py` instead of editing them by hand. The runtime
  needs no source checkout.
- The source language version is written only as `language_version` in
  `aa2modulus/language/policy.toml`, and code reads it from there. Version
  numbers quoted in docs are historical. Never write the number into code,
  tests or docs.
- The language server is implemented. Packaging (`package = false`),
  publishing and new editor features are separate tasks, started only when the
  user asks.
- The VS Code extension lives in its own repository, `aa2modulus-extension`.
  This repository owns the server side of their
  [wire contract](docs/lsp.md#client-contract).

## Doing the work

- Choose a coherent solution and simplify awkward designs when it helps. Add
  no compatibility layers or dependencies without a specific need. Keep
  confirmed binary and runtime requirements apart from open design choices.
- Every task gets a plan in `agent_data/plans/active/`, created from the
  template before you start. Follow `agent_data/plans/README.md`. A routine
  small edit needs no plan, only a work log entry. Routine means a few lines in
  one or two files, with no design choice and nothing left to hand over, such
  as a typo, a wording change or a one-line fix.
- Write and edit Python code by [Code style](docs/style.md). Fix the lines
  you touch that break it, but do not restyle code outside the task. If a rule
  in the guide gets in the way of clean code, raise it with the user instead
  of working around it, and update the guide when the user decides.
- Write tests by the [Tests](docs/style.md#tests) rules: one owner test per
  behaviour, expected values written by hand, in-process unless the test is
  about the process. Check how long a new test takes.
- Keep code, contracts, examples and the roadmap in sync.
- Run the checks that fit the change and any verification the user asked for.
  [Development](docs/development.md) lists the `mise` tasks. Report exactly
  what ran. Never claim that a check you did not run has passed.
- Do not install or upgrade tools, rewrite lock files, publish, create
  branches, issues or pull requests, or contact external services unless the
  user asks.

## Records and handover

- The work log is append-only. Add one entry per task, analysis included, at
  the end of `agent_data/WORK_LOG.md`, in date order. Never edit or delete
  earlier entries. Aim for 15 lines or fewer, link the plan instead of
  repeating it, and group file lists by directory.

  ```
  ## YYYY-MM-DD — <short title>
  - Outcome:
  - Files:
  - Checks: <exact commands and results>; not run: <...>
  - Decisions:
  - Follow-ups:
  ```

- Keep the plan's Handover section current whenever you stop: the current
  step, the next action, any partial state and open questions. Another agent
  must be able to resume from it.
- When a plan is finished, cancelled or superseded, record the outcome, move it
  to `agent_data/archive/<year>/`, add it to `agent_data/archive/README.md` and
  remove its row from the active index.
- `agent_data/ROADMAP.md` is the single status page. Update it when a
  capability, known limit or candidate item changes. Do not repeat status in
  the README, plan indexes or other docs.
- `TODO_FINDINGS.md` at the repository root is the owner's inbox. Triage each
  item into the roadmap or a plan, remove it from the inbox, and record where it
  went in the work log.
- Finish with a short summary of what changed, how you verified it, and what
  remains limited.

## Sub-agents

Use sub-agents for focused parts of one task, and state explicit, disjoint file
ownership in each prompt. The orchestrating agent owns the plan, the roadmap,
the work log, regeneration of generated references, and the final checks. It
reviews each sub-agent's diff and verifies its claims before accepting them.
Read-only audits may run in parallel and write their reports outside the
repository. Do not delegate routine reading of documents. Run project-wide
rewrites alone or in disjoint batches. Concurrent test runs may see other
agents' unfinished edits.
