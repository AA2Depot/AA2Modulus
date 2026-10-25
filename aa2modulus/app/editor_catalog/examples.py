"""Entry examples, kept only when they compile"""

from __future__ import annotations

from ...context.operation import SourceContext
from ..compile import CompileError, compile_source
from .entries import Draft, Report

# Examples compile in batches; a failing batch is retried one draft at a time.
BATCH_SIZE = 40


def attach(context: SourceContext, drafts: list[Draft], report: Report) -> None:
    candidates = []
    for draft in drafts:
        if draft.body is None:
            report.omitted_examples.append(
                (draft.entry["id"], draft.note or "no natural call form")
            )
        else:
            candidates.append(draft)

    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start : start + BATCH_SIZE]
        if _error(context, batch) is None:
            for draft in batch:
                _set(draft)
            continue

        for draft in batch:
            error = _error(context, [draft])
            if error is None:
                _set(draft)
            else:
                report.omitted_examples.append((draft.entry["id"], error))


def trigger(event: str, body: str, name: str = "Example") -> str:
    lines = [f'trigger "{name}" {{', f"  on {event};"]
    lines += [f"  {line}" for line in body.splitlines()]
    lines.append("}")
    return "\n".join(lines)


def _error(context: SourceContext, drafts: list[Draft]) -> str | None:
    """First compile error of one module holding a trigger per draft, else None."""

    triggers = "\n".join(
        trigger(draft.event, draft.body or "", f"Example {index}")
        for index, draft in enumerate(drafts)
    )
    try:
        compile_source(f'module "Examples" {{\n{triggers}\n}}\n', context=context)
    except CompileError as error:
        return str(error).splitlines()[0]
    return None


def _set(draft: Draft) -> None:
    """An event's example is the whole trigger; any other is its statement."""

    assert draft.body is not None
    if draft.entry["kind"] == "event":
        draft.entry["example"] = trigger(draft.event, draft.body)
    else:
        draft.entry["example"] = draft.body
