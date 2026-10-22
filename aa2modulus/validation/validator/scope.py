"""Variable bindings visible to a validated expression."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ...model.records import GlobalVariable, Variable
from ...model.types import TypeId


@dataclass(frozen=True, slots=True)
class VariableBinding:
    name: str
    type: TypeId
    scope: str
    node: GlobalVariable | Variable | None


@dataclass(slots=True)
class Scope:
    """Module (or card) globals, then the current trigger's locals.

    Argument variables, when set, replace both: definition arguments are checked
    against their formal types only.
    """

    globals: dict[str, VariableBinding] = field(default_factory=dict)
    locals: dict[str, VariableBinding] = field(default_factory=dict)
    arguments: Mapping[str, TypeId] | None = None

    def lookup(self, name: str) -> VariableBinding | None:
        if self.arguments is not None:
            type_id = self.arguments.get(name)
            return None if type_id is None else VariableBinding(name, type_id, "argument", None)
        global_binding = self.globals.get(name)
        if global_binding is not None:
            return global_binding
        return self.locals.get(name)
