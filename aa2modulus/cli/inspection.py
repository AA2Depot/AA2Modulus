"""Deterministic human-readable rendering for decoded module inspection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TextIO

from ..binary.reader import TrailingBytes
from ..core.diagnostics import Diagnostic, ValidationResult, format_path
from ..language.operators import OPERATOR_SYNTAX
from ..model.control_flow import (
    ACTION_CONDBREAK,
    ACTION_CONDCONTINUE,
    ACTION_CONDJUMP,
    ACTION_ELSEIF,
    ACTION_IF,
)
from ..model.display import replace_parameters, type_name, value_text
from ..model.records import (
    ActionCall,
    Event,
    Expression,
    GlobalVariable,
    GuiAction,
    Module,
    Trigger,
)
from ..model.types import EXPR_CONSTANT, EXPR_NAMEDCONSTANT, EXPR_VAR, ValueType
from .render.breadcrumb import breadcrumb, unlocated_notes
from .render.diagnostics import render_diagnostic
from .render.terminal import RenderOptions

_COMPARISONS = frozenset({"==", "!=", "<", "<=", ">", ">="})
# Only these exact native templates establish grouping around a condition.
_CONDITION_TEMPLATES = {
    ACTION_IF: ("If (%p) then", (ValueType.BOOL,), 0),
    ACTION_ELSEIF: ("Else If (%p) then", (ValueType.BOOL,), 0),
    ACTION_CONDJUMP: ("Jump %p Actions if (%p)", (ValueType.INT, ValueType.BOOL), 1),
    ACTION_CONDBREAK: ("Break If (%p)", (ValueType.BOOL,), 0),
    ACTION_CONDCONTINUE: ("Continue If (%p)", (ValueType.BOOL,), 0),
    17: ("End Thread If (%p)", (ValueType.BOOL,), 0),
}


@dataclass(frozen=True, slots=True)
class _RenderedExpression:
    text: str
    conservative: str
    precedence: int = 0
    token: str | None = None

    def operand(self, precedence: int, *, comparison: bool = False) -> str:
        if self.token is None:
            # Opaque GUI labels retain their original rendering; infer no syntax.
            return self.conservative
        if self.precedence < precedence or (comparison and self.token in _COMPARISONS):
            return f"({self.text})"
        return self.text


def _safe_text(value: str) -> str:
    return value.encode("utf-8", "backslashreplace").decode("utf-8")


def _render_expression(expression: Expression) -> _RenderedExpression:
    if expression.id == EXPR_CONSTANT and expression.constant is not None:
        text = value_text(expression.constant)
    elif expression.id == EXPR_VAR:
        text = f"var({_safe_text(expression.variable_name or '')})"
    elif expression.id == EXPR_NAMEDCONSTANT and expression.named_constant is not None:
        reference = expression.named_constant
        if reference.metadata is not None:
            text = _safe_text(reference.metadata.interactive_name or reference.metadata.name)
        else:
            text = (
                f"UNKNOWN_NAMED_CONSTANT(type={type_name(reference.value_type)}, id={reference.id})"
            )
    else:
        parameters = tuple(_render_expression(parameter) for parameter in expression.parameters)
        conservative = tuple(parameter.conservative for parameter in parameters)
        metadata = expression.metadata
        if metadata is None:
            text = (
                f"UNKNOWN_EXPRESSION(type={type_name(expression.return_type)}, id={expression.id})"
                + (f"({', '.join(conservative)})" if parameters else "")
            )
        else:
            template = metadata.interactive_name or metadata.name
            text = _safe_text(replace_parameters(template, conservative))
            if (
                metadata.id == expression.id
                and metadata.return_type == expression.return_type
                and metadata.declared_return_type == expression.return_type
                and metadata.parameter_types
                == tuple(parameter.return_type for parameter in expression.parameters)
            ):
                for token, (precedence, fixity, associativity, _) in OPERATOR_SYNTAX.items():
                    if fixity == "prefix" and template == f"{token}(%p)" and len(parameters) == 1:
                        compact = f"{token}{parameters[0].operand(precedence)}"
                    elif (
                        fixity == "infix"
                        and template == f"(%p {token} %p)"
                        and len(parameters) == 2
                    ):
                        comparison = token in _COMPARISONS
                        left = parameters[0].operand(
                            precedence + (associativity == "right"), comparison=comparison
                        )
                        # Keep equal-precedence right trees, even for +, *, &&,
                        # and ||: flattening would assume algebraic associativity.
                        right = parameters[1].operand(
                            precedence + (associativity == "left"), comparison=comparison
                        )
                        compact = f"{left} {token} {right}"
                    else:
                        continue
                    return _RenderedExpression(compact, text, precedence, token)
    return _RenderedExpression(text, text)


def _expression_text(expression: Expression) -> str:
    return _render_expression(expression).text


def _expression_display(expression: Expression) -> str:
    return (
        f"{_expression_text(expression)} "
        f"[type={type_name(expression.return_type)}, id={expression.id}]"
    )


def _action_text(action: ActionCall) -> str:
    rendered = tuple(_render_expression(parameter) for parameter in action.parameters)
    parameters = tuple(parameter.conservative for parameter in rendered)
    if action.metadata is not None:
        template = action.metadata.interactive_name or action.metadata.name
        condition = _CONDITION_TEMPLATES.get(action.id)
        if (
            condition is not None
            and action.metadata.id == action.id
            and template == condition[0]
            and action.metadata.parameter_types == condition[1]
            and tuple(parameter.return_type for parameter in action.parameters) == condition[1]
        ):
            parameters = tuple(
                parameter.text if index == condition[2] else parameter.conservative
                for index, parameter in enumerate(rendered)
            )
        return _safe_text(replace_parameters(template, parameters))
    return f"UNKNOWN_ACTION(id={action.id})" + (f"({', '.join(parameters)})" if parameters else "")


def _event_name(event: Event) -> str:
    if event.metadata is not None:
        return _safe_text(event.metadata.name)
    return f"UNKNOWN_EVENT_{event.id}"


def _print_expression_parameters(
    expressions: tuple[Expression, ...],
    indent: str,
    output: TextIO,
) -> None:
    for index, expression in enumerate(expressions, start=1):
        print(f"{indent}parameter {index}: {_expression_display(expression)}", file=output)


def _print_action(action: GuiAction, indent: str, output: TextIO) -> None:
    print(f"{indent}- {_action_text(action.action)} [action id={action.action.id}]", file=output)
    _print_expression_parameters(action.action.parameters, indent + "  ", output)
    for child in action.children:
        _print_action(child, indent + "  ", output)


def _print_global(variable: GlobalVariable, output: TextIO) -> None:
    print(
        f"  - {_safe_text(variable.name)} (type={type_name(variable.type)}, "
        f"default={value_text(variable.default_value)}, "
        f"current={value_text(variable.current_value)}, "
        f"initialized={'true' if variable.initialized else 'false'})",
        file=output,
    )


def _print_trigger(index: int, trigger: Trigger, output: TextIO) -> None:
    print(file=output)
    print(f"[{index}] Trigger: {_safe_text(trigger.name)}", file=output)
    print("  Events:", file=output)
    if trigger.events:
        for event in trigger.events:
            parameters = tuple(_expression_text(item) for item in event.parameters)
            suffix = f" ({', '.join(parameters)})" if parameters else ""
            print(f"    - {_event_name(event)} [event id={event.id}]{suffix}", file=output)
            _print_expression_parameters(event.parameters, "      ", output)
    else:
        print("    (none)", file=output)

    print("  Local variables:", file=output)
    if trigger.variables:
        for variable in trigger.variables:
            print(
                f"    - {_safe_text(variable.name)} (type={type_name(variable.type)}, "
                f"default={_expression_display(variable.default_expression)})",
                file=output,
            )
    else:
        print("    (none)", file=output)

    print("  Actions:", file=output)
    if trigger.gui_actions:
        for action in trigger.gui_actions:
            _print_action(action, "    ", output)
    else:
        print("    (none)", file=output)


def _print_module(module: Module, output: TextIO) -> None:
    print(f"Module: {_safe_text(module.name)}", file=output)
    print(f"Description: {_safe_text(module.description)}", file=output)
    print("Dependencies:", file=output)
    if module.dependencies:
        for dependency in module.dependencies:
            print(f"  - {_safe_text(dependency)}", file=output)
    else:
        print("  (none)", file=output)

    print("Global variables:", file=output)
    if module.globals:
        for variable in module.globals:
            _print_global(variable, output)
    else:
        print("  (none)", file=output)

    print(f"Triggers: {len(module.triggers)}", file=output)
    for index, trigger in enumerate(module.triggers, start=1):
        _print_trigger(index, trigger, output)


def _diagnostic_lines(
    diagnostic: Diagnostic,
    module: Module,
    options: RenderOptions,
) -> list[str]:
    """One readable entry: headline, then breadcrumb with hex offset, notes and help."""

    if options.format == "short":
        text = render_diagnostic(diagnostic, options=options)
        return text.split("\n")
    headline = f"{diagnostic.severity}[{diagnostic.code}]: {diagnostic.message}"
    if options.color:
        headline = render_diagnostic(diagnostic, options=options).split("\n", 1)[0]
    lines = [headline]
    where = []
    crumb = breadcrumb(diagnostic.path, module=module, separator=options.separator)
    if diagnostic.path:
        where.append(crumb)
    if diagnostic.offset is not None:
        where.append(f"offset 0x{diagnostic.offset:X}")
    if where:
        lines.append(f"    at {', '.join(where)}")
    notes = unlocated_notes(diagnostic, crumb) if diagnostic.path else diagnostic.notes
    lines.extend(f"    note: {note}" for note in notes)
    if diagnostic.help:
        lines.append(f"    help: {diagnostic.help}")
    return lines


def _print_diagnostics(
    module: Module,
    validation: ValidationResult,
    options: RenderOptions,
    output: TextIO,
) -> None:
    if not validation.diagnostics:
        return
    print(file=output)
    print("Diagnostics:", file=output)
    for diagnostic in validation.diagnostics:
        first, *rest = _diagnostic_lines(diagnostic, module, options)
        print(f"  - {first}", file=output)
        for line in rest:
            print(f"  {line}", file=output)
        if options.verbose and options.format == "human" and diagnostic.path:
            print(f"    path {format_path(diagnostic.path)}", file=output)


def write_inspection(
    module: Module,
    validation: ValidationResult,
    *,
    trailing_bytes: TrailingBytes | None,
    output: TextIO,
    options: RenderOptions | None = None,
) -> None:
    """Write inspection output without performing I/O or exit-code decisions."""

    _print_module(module, output)
    if trailing_bytes is not None:
        print(file=output)
        print(
            f"Warning: {trailing_bytes.count} trailing bytes remain "
            f"at offset 0x{trailing_bytes.offset:X}.",
            file=output,
        )
    _print_diagnostics(module, validation, options or RenderOptions(), output)
