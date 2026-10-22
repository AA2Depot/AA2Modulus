"""Module, global and trigger checks, and the validation entry points."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from ...core.diagnostics import ValidationResult
from ...language.catalog.build import build_language_catalog
from ...language.catalog.model import LanguageCatalog
from ...language.loader import load_language_policy
from ...metadata.loader import load_metadata
from ...metadata.snapshot import MetadataSnapshot
from ...model.display import type_name
from ...model.records import Expression, Module, Trigger
from ...model.types import TypeId
from ..projection import ProjectedAction, ProjectionError, project_gui_actions
from .declarations import module_declaration_anchor
from .expressions import validate_expression
from .reporter import Reporter
from .scope import VariableBinding
from .state import ValidatorState
from .statements import validate_action, validate_event, validate_gui_action
from .value_types import check_declared_type

_VALIDATION_CATALOGS: dict[int, tuple[MetadataSnapshot, LanguageCatalog]] = {}


def _validation_catalog(metadata: MetadataSnapshot) -> LanguageCatalog:
    """Reuse the shipped-policy catalog for repeated validation of one snapshot."""

    key = id(metadata)
    cached = _VALIDATION_CATALOGS.get(key)
    if cached is not None and cached[0] is metadata:
        return cached[1]
    catalog = build_language_catalog(metadata, load_language_policy(metadata=metadata))
    if len(_VALIDATION_CATALOGS) >= 8:
        _VALIDATION_CATALOGS.clear()
    _VALIDATION_CATALOGS[key] = (metadata, catalog)
    return catalog


def validate_expression_in_scope(
    expression: Expression,
    metadata: MetadataSnapshot,
    *,
    filename: str,
    variables: Mapping[str, TypeId],
    catalog: LanguageCatalog | None = None,
) -> ValidationResult:
    """Check an argument before substitution can discard it, using SIR rules.

    Scope supplies types by lookup without synthesizing or copying declarations.
    These checks never enter serialized output or invent caller variables.
    """

    state = ValidatorState(metadata, Reporter(filename), "strict", catalog)
    state.scope.arguments = variables
    validate_expression(state, expression, (), ())
    return ValidationResult(tuple(state.reporter.diagnostics))


def validate_module(
    module: Module,
    *,
    metadata: MetadataSnapshot | None = None,
    filename: str = "<module>",
    profile: Literal["strict", "native"] = "strict",
    catalog: LanguageCatalog | None = None,
) -> ValidationResult:
    """Validate authoring rules (default) or pinned native initialization checks.

    Raw provenance does not relax source or model validation. Structural recovery
    uses decode_module/encode_module without claiming semantic validity.
    Native validation uses projected actions and never relaxes raw provenance;
    successful initialization checks do not establish safe Value evaluation.
    Dependency names are retained metadata: empty, self and duplicate names are
    strict errors or native warnings. A name never loads a module or supplies globals.
    """

    if not filename:
        raise ValueError("filename cannot be empty")
    if profile not in ("strict", "native"):
        raise ValueError("profile must be 'strict' or 'native'")
    if metadata is None:
        metadata = load_metadata()
    if catalog is not None and catalog.metadata is not metadata:
        raise ValueError("catalog must be built from the same metadata provider")
    if catalog is None:
        # The shipped policy supplies source spellings for messages and its
        # defect table; reviewed native facts are policy-independent.
        catalog = _validation_catalog(metadata)
    state = ValidatorState(metadata, Reporter(filename), profile, catalog)
    return _validate(state, module)


def _validate(state: ValidatorState, module: Module) -> ValidationResult:
    state.declaration_anchor = module_declaration_anchor(module)
    _validate_dependencies(state, module)
    _register_globals(state, module)
    _validate_globals(state, module)
    for index, trigger in enumerate(module.triggers):
        _validate_trigger(state, trigger, ("triggers", index))
    return ValidationResult(tuple(state.reporter.diagnostics))


def _register_globals(state: ValidatorState, module: Module) -> None:
    bindings: dict[str, VariableBinding] = {}
    state.scope.globals = bindings
    for index, global_variable in enumerate(module.globals):
        path: tuple[str | int, ...] = ("globals", index)
        check_declared_type(state, global_variable, path, "global variable")
        if global_variable.name in bindings:
            state.reporter.add(
                global_variable,
                path,
                "DUPLICATE_GLOBAL_VARIABLE",
                f"global variable {global_variable.name!r} is declared more than once",
                field_path=("name",),
                severity=state.authoring_severity,
            )
            continue
        bindings[global_variable.name] = VariableBinding(
            global_variable.name, global_variable.type, "global", global_variable
        )


def _register_locals(
    state: ValidatorState, trigger: Trigger, trigger_path: tuple[str | int, ...]
) -> None:
    bindings: dict[str, VariableBinding] = {}
    state.scope.locals = bindings
    for index, local_variable in enumerate(trigger.variables):
        path = (*trigger_path, "variables", index)
        check_declared_type(state, local_variable, path, "local variable")
        if local_variable.name in bindings:
            state.reporter.add(
                local_variable,
                path,
                "DUPLICATE_LOCAL_VARIABLE",
                f"local variable {local_variable.name!r} is declared more than once",
                field_path=("name",),
                severity=state.authoring_severity,
            )
            continue
        bindings[local_variable.name] = VariableBinding(
            local_variable.name, local_variable.type, "local", local_variable
        )


def _validate_trigger(state: ValidatorState, trigger: Trigger, path: tuple[str | int, ...]) -> None:
    state.reporter.trigger_name = trigger.name or None
    try:
        _validate_trigger_body(state, trigger, path)
    finally:
        state.reporter.trigger_name = None


def _validate_trigger_body(
    state: ValidatorState, trigger: Trigger, path: tuple[str | int, ...]
) -> None:
    state.trigger_event_ids = tuple(event.id for event in trigger.events)
    _register_locals(state, trigger, path)
    projected = _project(state, trigger, path)
    if state.native:
        _resolve_variables(state, trigger, projected, path)
    for index, event in enumerate(trigger.events):
        validate_event(state, event, path, (*path, "events", index))
    for index, variable in enumerate(trigger.variables):
        expression_path = (*path, "variables", index, "default_expression")
        validate_expression(state, variable.default_expression, path, expression_path)
        if state.expression_type(variable.default_expression) != variable.type:
            state.reporter.add(
                variable.default_expression,
                expression_path,
                "VARIABLE_DEFAULT_TYPE",
                f"local variable {variable.name!r} expects default type "
                f"{type_name(variable.type)}, found "
                f"{type_name(state.expression_type(variable.default_expression))}",
            )
    if state.native:
        for item in projected:
            validate_action(state, item.action, path, (*path, "gui_actions", *item.path, "action"))
    else:
        for index, action in enumerate(trigger.gui_actions):
            validate_gui_action(state, action, path, (*path, "gui_actions", index))


def _project(
    state: ValidatorState, trigger: Trigger, path: tuple[str | int, ...]
) -> tuple[ProjectedAction, ...]:
    """Flatten the GUI tree as AAUnlimited does, reporting what the projection drops."""

    try:
        projected, discarded = project_gui_actions(trigger.gui_actions)
    except ProjectionError as exc:
        if state.native:
            state.reporter.add(
                exc.node.action,
                (*path, "gui_actions", *exc.path, "action"),
                "NATIVE_PROJECTION_ERROR",
                exc.message,
            )
        return ()
    for control in discarded:
        state.reporter.add(
            control.node.action,
            (*path, "gui_actions", *control.path, "action"),
            "NATIVE_DISCARDED_CONTROL",
            "native projection discards this loop control because no loop state "
            "is active here; conditional children start fresh loop state",
            severity="warning",
        )
    return projected


def _resolve_variables(
    state: ValidatorState,
    trigger: Trigger,
    projected: tuple[ProjectedAction, ...],
    path: tuple[str | int, ...],
) -> None:
    """The native pre-pass: report undefined variables in initialization order."""

    state.resolving_only = True
    for index, event in enumerate(trigger.events):
        for argument, expression in enumerate(event.parameters):
            validate_expression(
                state, expression, path, (*path, "events", index, "parameters", argument)
            )
    for index, variable in enumerate(trigger.variables):
        validate_expression(
            state,
            variable.default_expression,
            path,
            (*path, "variables", index, "default_expression"),
        )
    for item in projected:
        for argument, expression in enumerate(item.action.parameters):
            validate_expression(
                state,
                expression,
                path,
                (*path, "gui_actions", *item.path, "action", "parameters", argument),
            )
    state.resolving_only = False


def _validate_globals(state: ValidatorState, module: Module) -> None:
    for index, variable in enumerate(module.globals):
        path = ("globals", index)
        if variable.default_value.type != variable.type:
            state.reporter.add(
                variable.default_value,
                (*path, "default_value"),
                "GLOBAL_DEFAULT_TYPE",
                f"global variable {variable.name!r} expects default type "
                f"{type_name(variable.type)}, found "
                f"{type_name(variable.default_value.type)}",
                severity=state.authoring_severity,
            )
        if variable.current_value.type != variable.type:
            state.reporter.add(
                variable.current_value,
                (*path, "current_value"),
                "GLOBAL_CURRENT_TYPE",
                f"global variable {variable.name!r} expects current type "
                f"{type_name(variable.type)}, found "
                f"{type_name(variable.current_value.type)}",
                severity=state.authoring_severity,
            )


def _validate_dependencies(state: ValidatorState, module: Module) -> None:
    seen: set[str] = set()
    severity = state.authoring_severity
    for index, dependency in enumerate(module.dependencies):
        path = ("dependencies", index)
        if not dependency.strip():
            state.reporter.add(
                module,
                (),
                "INVALID_MODULE_DEPENDENCY",
                "module dependency cannot be empty",
                severity=severity,
                field_path=path,
            )
        if dependency == module.name:
            state.reporter.add(
                module,
                (),
                "INVALID_MODULE_DEPENDENCY",
                f"module cannot depend on itself: {dependency!r}",
                severity=severity,
                field_path=path,
            )
        if dependency in seen:
            state.reporter.add(
                module,
                (),
                "DUPLICATE_MODULE_DEPENDENCY",
                f"module dependency {dependency!r} is listed more than once",
                severity=severity,
                field_path=path,
            )
        seen.add(dependency)
