"""Transformer rules: The unit root, imports, the module header, constants and globals."""

from __future__ import annotations

from lark import v_args
from lark.tree import Meta

from ...ast import (
    SourceConstant,
    SourceConstantReference,
    SourceGlobal,
    SourceImport,
    SourceMacro,
    SourceModule,
    SourceName,
    SourceTrigger,
    SourceTriggerImport,
    SourceTriggerTemplate,
    SourceUnit,
)
from ..spans import meta_span, token_span
from .base import (
    Dependency,
    Description,
    NamedValue,
    TransformerBase,
    as_const_value,
    as_literal,
    as_named,
    as_source_type,
    as_token,
    as_type_id,
)


@v_args(meta=True)
class DeclarationsMixin(TransformerBase):
    def start(self, meta: Meta, children: list[object]) -> SourceModule | SourceUnit:
        modules = [child for child in children if isinstance(child, SourceModule)]
        macros = tuple(child for child in children if isinstance(child, SourceMacro))
        imports = tuple(child for child in children if isinstance(child, SourceImport))
        templates = tuple(child for child in children if isinstance(child, SourceTriggerTemplate))
        constants = tuple(child for child in children if isinstance(child, SourceConstant))
        if len(modules) > 1 or len(modules) + len(macros) + len(imports) + len(templates) + len(
            constants
        ) != len(children):
            self._fail(meta, "a source unit may contain at most one module")
        module = modules[0] if modules else None
        if (
            module is not None
            and not macros
            and not imports
            and not templates
            and not constants
            and not self.allows
            and len(children) == 1
        ):
            return module
        return SourceUnit(
            module,
            macros,
            source_span=meta_span(meta, self.filename),
            imports=imports,
            templates=templates,
            constants=constants,
            allows=tuple(
                sorted(
                    self.allows,
                    key=lambda item: (item.source_span.start_line, item.source_span.start_column),
                )
            ),
        )

    def import_decl(self, meta: Meta, children: list[object]) -> SourceImport:
        token = as_token(children[0])
        return SourceImport(
            self._string(token),
            source_span=meta_span(meta, self.filename),
            path_span=token_span(token, self.filename),
        )

    def module(self, meta: Meta, children: list[object]) -> SourceModule:
        name_token = as_token(children[0])
        name = self._string(name_token)
        description = ""
        dependencies: list[str] = []
        globals_: list[SourceGlobal] = []
        constants: list[SourceConstant] = []
        triggers: list[SourceTrigger | SourceTriggerImport] = []
        for child in children[1:]:
            if isinstance(child, Description):
                description = child.value
            elif isinstance(child, Dependency):
                dependencies.append(child.value)
            elif isinstance(child, SourceGlobal):
                globals_.append(child)
            elif isinstance(child, SourceConstant):
                constants.append(child)
            elif isinstance(child, (SourceTrigger, SourceTriggerImport)):
                triggers.append(child)
            else:
                self._fail(meta, f"unsupported module item {child!r}")
        return SourceModule(
            name,
            description,
            tuple(dependencies),
            tuple(globals_),
            tuple(triggers),
            source_span=meta_span(meta, self.filename),
            name_span=token_span(name_token, self.filename),
            constants=tuple(constants),
        )

    def description(self, meta: Meta, children: list[object]) -> Description:
        token = as_token(children[0])
        if token.type == "BLOCK_STRING":
            return Description(self._block_string(token))
        return Description(self._string(token))

    def depends_on(self, meta: Meta, children: list[object]) -> Dependency:
        return Dependency(self._string(as_token(children[0])))

    def const_decl(self, meta: Meta, children: list[object]) -> SourceConstant:
        name = as_named(children[0])
        self._check_bare_name(name)
        return SourceConstant(
            name.value,
            as_type_id(children[1]),
            as_const_value(children[2]),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
            quoted_name=name.quoted,
        )

    def const_name(self, meta: Meta, children: list[object]) -> SourceName:
        token = as_token(children[0])
        span = token_span(token, self.filename)
        self._check_bare_name(NamedValue(str(token), span), "constant")
        return SourceName(str(token), source_span=span, name_span=span)

    def const_ref(self, meta: Meta, children: list[object]) -> SourceConstantReference:
        token = as_token(children[0])
        return SourceConstantReference(
            self._string(token),
            source_span=meta_span(meta, self.filename),
            name_span=token_span(token, self.filename),
        )

    def global_decl(self, meta: Meta, children: list[object]) -> SourceGlobal:
        name = as_named(children[0])
        self._check_bare_name(name)
        return SourceGlobal(
            name.value,
            as_source_type(children[1]),
            default=as_const_value(children[2]),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
            quoted_name=name.quoted,
        )

    def global_state_decl(self, meta: Meta, children: list[object]) -> SourceGlobal:
        name = as_named(children[0])
        self._check_bare_name(name)
        return SourceGlobal(
            name.value,
            as_source_type(children[1]),
            default=as_literal(children[2]),
            current=as_literal(children[3]),
            initialized=str(children[4]) == "true",
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
            quoted_name=name.quoted,
        )
