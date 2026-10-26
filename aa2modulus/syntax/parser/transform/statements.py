"""Transformer rules: Blocks, control flow, assignments and actions."""

from __future__ import annotations

from lark import v_args
from lark.tree import Meta

from ....core.locations import SourceSpan
from ....core.source_names import is_source_name
from ...ast import (
    SourceAction,
    SourceAssignment,
    SourceElse,
    SourceElseIf,
    SourceFor,
    SourceIf,
    SourceLoop,
    SourceLoopControl,
    SourceMemberAction,
    SourceMemberProperty,
    SourceName,
)
from ...hints import FOREIGN_KEYWORD_HELP
from ...spans import qualified_segment_spans
from ..spans import meta_span, token_span
from .base import (
    Block,
    NamedValue,
    TransformerBase,
    as_expression,
    as_expressions,
    as_named,
    as_statement,
    as_statements,
    as_token,
)


@v_args(meta=True)
class StatementsMixin(TransformerBase):
    def block(self, meta: Meta, children: list[object]) -> Block:
        return Block(
            tuple(as_statement(child) for child in children), meta_span(meta, self.filename)
        )

    def if_stmt(self, meta: Meta, children: list[object]) -> SourceIf:
        condition = as_expression(children[0])
        body = as_statements(children[1])
        else_if: list[SourceElseIf] = []
        else_branch: SourceElse | None = None
        for branch in children[2:]:
            if isinstance(branch, SourceElseIf):
                else_if.append(branch)
            elif isinstance(branch, SourceElse):
                else_branch = branch
            else:
                raise TypeError(f"unexpected if branch {branch!r}")
        return SourceIf(
            condition=condition,
            body=body,
            else_if=tuple(else_if),
            else_branch=else_branch,
            source_span=meta_span(meta, self.filename),
        )

    def elseif_clause(self, meta: Meta, children: list[object]) -> SourceElseIf:
        return SourceElseIf(
            as_expression(children[0]),
            as_statements(children[1]),
            source_span=meta_span(meta, self.filename),
        )

    def else_clause(self, meta: Meta, children: list[object]) -> SourceElse:
        return SourceElse(as_statements(children[0]), source_span=meta_span(meta, self.filename))

    def standalone_elseif_stmt(self, meta: Meta, children: list[object]) -> SourceElseIf:
        return SourceElseIf(
            as_expression(children[1]),
            as_statements(children[2]),
            source_span=meta_span(meta, self.filename),
        )

    def standalone_else_empty(self, meta: Meta, children: list[object]) -> SourceElse:
        return SourceElse(source_span=meta_span(meta, self.filename))

    def standalone_else_block(self, meta: Meta, children: list[object]) -> SourceElse:
        return SourceElse(as_statements(children[1]), source_span=meta_span(meta, self.filename))

    def loop_stmt(self, meta: Meta, children: list[object]) -> SourceLoop:
        return SourceLoop(as_statements(children[0]), source_span=meta_span(meta, self.filename))

    def for_stmt(self, meta: Meta, children: list[object]) -> SourceFor:
        target = as_named(children[0])
        self._check_bare_name(target)
        return SourceFor(
            target.value,
            as_expression(children[1]),
            as_expression(children[2]),
            as_statements(children[3]),
            source_span=meta_span(meta, self.filename),
            target_span=target.span,
            quoted_name=target.quoted,
        )

    def loop_control(self, meta: Meta, children: list[object]) -> SourceLoopControl:
        return SourceLoopControl(
            str(children[0]),
            as_expression(children[1]) if len(children) > 1 else None,
            source_span=meta_span(meta, self.filename),
        )

    def assignment(self, meta: Meta, children: list[object]) -> SourceAssignment:
        target = as_named(children[0])
        return SourceAssignment(
            target.value,
            as_expression(children[1]),
            source_span=meta_span(meta, self.filename),
            target_span=target.span,
            explicit_variable=target.explicit_variable,
        )

    def assignment_identifier(self, meta: Meta, children: list[object]) -> NamedValue:
        token = as_token(children[0])
        target = NamedValue(self._identifier(token), token_span(token, self.filename))
        self._check_bare_name(target, "assignment")
        return target

    def assignment_variable(self, meta: Meta, children: list[object]) -> NamedValue:
        token = as_token(children[0])
        return NamedValue(self._string(token), token_span(token, self.filename), True)

    def bare_name_ref(self, meta: Meta, children: list[object]) -> NamedValue:
        token = as_token(children[0])
        return NamedValue(self._identifier(token), token_span(token, self.filename))

    def string_name_ref(self, meta: Meta, children: list[object]) -> NamedValue:
        token = as_token(children[0])
        return NamedValue(self._string(token), token_span(token, self.filename), quoted=True)

    def source_name(self, meta: Meta, children: list[object]) -> NamedValue:
        token = as_token(children[0])
        name = str(token)
        if not is_source_name(name):
            code = "INVALID_SOURCE_NAME" if "." in name else "SYNTAX_ERROR"
            self._fail(
                meta,
                f"invalid source name {name!r}",
                code,
                help=FOREIGN_KEYWORD_HELP.get(name.casefold()),
            )
        return NamedValue(name, token_span(token, self.filename))

    def action_empty(self, meta: Meta, children: list[object]) -> SourceAction:
        name = as_named(children[0])
        return SourceAction(
            name=name.value,
            arguments=as_expressions(children[1]) if len(children) > 1 else (),
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
        )

    def action_block(self, meta: Meta, children: list[object]) -> SourceAction:
        name = as_named(children[0])
        arguments = as_expressions(children[1]) if len(children) == 3 else ()
        block = children[-1]
        return SourceAction(
            name=name.value,
            arguments=arguments,
            children=as_statements(block),
            has_block=True,
            source_span=meta_span(meta, self.filename),
            name_span=name.span,
            block_span=block.span if isinstance(block, Block) else None,
        )

    def member_action_stmt(self, meta: Meta, children: list[object]) -> SourceMemberAction:
        receiver, member, member_span = self._member_chain(
            as_expression(children[0]), as_token(children[1])
        )
        return SourceMemberAction(
            receiver,
            member,
            as_expressions(children[2]) if len(children) > 2 else (),
            source_span=meta_span(meta, self.filename),
            name_span=member_span,
        )

    def bare_member_stmt(self, meta: Meta, children: list[object]) -> SourceMemberAction:
        """Keep ``receiver.Member;`` as a node so the binder reports ``MEMBER_KIND``."""

        child = children[0]
        span = meta_span(meta, self.filename)
        if isinstance(child, SourceMemberProperty):
            return SourceMemberAction(
                child.receiver,
                child.member,
                (),
                source_span=span,
                name_span=child.name_span,
                has_parentheses=False,
            )
        token = as_token(child)
        name = str(token)
        parts = name.split(".")
        spans = qualified_segment_spans(name, token_span(token, self.filename))
        receiver_name = ".".join(parts[:-1])
        first, before_last = spans[0], spans[-2] if len(spans) > 1 else None
        receiver_span = (
            SourceSpan(
                first.filename,
                first.start_line,
                first.start_column,
                before_last.end_line,
                before_last.end_column,
            )
            if first is not None and before_last is not None
            else None
        )
        return SourceMemberAction(
            SourceName(receiver_name, source_span=receiver_span, name_span=receiver_span),
            parts[-1],
            (),
            source_span=span,
            name_span=spans[-1],
            has_parentheses=False,
        )

    def raw_action_empty(self, meta: Meta, children: list[object]) -> SourceAction:
        return SourceAction(
            identifier=self._int(as_token(children[0])),
            arguments=as_expressions(children[1]) if len(children) > 1 else (),
            source_span=meta_span(meta, self.filename),
        )

    def raw_action_block(self, meta: Meta, children: list[object]) -> SourceAction:
        arguments = as_expressions(children[1]) if len(children) == 3 else ()
        return SourceAction(
            identifier=self._int(as_token(children[0])),
            arguments=arguments,
            children=as_statements(children[-1]),
            has_block=True,
            source_span=meta_span(meta, self.filename),
        )

    def raw_action_plain(self, meta: Meta, children: list[object]) -> SourceAction:
        return SourceAction(
            identifier=self._int(as_token(children[0])), source_span=meta_span(meta, self.filename)
        )
