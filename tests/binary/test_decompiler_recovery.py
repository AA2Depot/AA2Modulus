"""Recovery diagnostics from hand-packed native records."""

from __future__ import annotations

import struct

import pytest

from aa2modulus.app.compile import CompileError, compile_source
from aa2modulus.app.decompile import decompile_module
from aa2modulus.binary.writer import encode_module
from tests.support.regression_data import undefined_variables_module
from tests.support.source import parse_module
from tests.support.wire import pack_expression, pack_string, pack_vector


def _action(
    identifier: int, parameters: tuple[bytes, ...] = (), children: tuple[bytes, ...] = ()
) -> bytes:
    return struct.pack("<i", identifier) + pack_vector(*parameters) + pack_vector(*children)


def _trigger(
    name: str,
    *,
    events: tuple[bytes, ...] = (),
    variables: tuple[bytes, ...] = (),
    actions: tuple[bytes, ...] = (),
) -> bytes:
    return (
        pack_string(name) + pack_vector(*events) + pack_vector(*variables) + pack_vector(*actions)
    )


def _module(*triggers: bytes) -> bytes:
    return (
        pack_string("M") + pack_string("") + pack_vector(*triggers) + pack_vector() + pack_vector()
    )


def test_unknown_native_event_and_action_keep_ids_and_binary_locations(metadata):
    event = struct.pack("<iI", 999, 0)
    action = struct.pack("<iII", 999, 0, 0)
    trigger = pack_string("Init") + struct.pack("<I", 1) + event + struct.pack("<I", 0)
    trigger += struct.pack("<I", 1) + action
    binary = pack_string("Unknown") + pack_string("") + struct.pack("<I", 1) + trigger
    binary += struct.pack("<II", 0, 0)

    result = decompile_module(
        binary,
        metadata=metadata,
        filename="unknown.bin",
        source_filename="unknown.aa2m",
        reject_trailing=True,
    )
    assert "raw_event 999" in result.source
    assert "raw_action 999" in result.source
    lines = result.source.splitlines()
    located = {
        item.code: lines[item.line - 1][item.column - 1 :]
        for item in result.diagnostics
        if item.filename == "unknown.aa2m" and item.offset is not None
    }
    assert located["UNKNOWN_EVENT"].startswith("raw_event 999")
    assert located["UNKNOWN_ACTION"].startswith("raw_action 999")


@pytest.mark.parametrize(
    ("actions", "fragments"),
    (
        ((_action(4),), ("Else;",)),
        ((_action(3, (pack_expression(2, 1, struct.pack("<iB", 2, 0)),)),), ("ElseIf (false)",)),
        (
            (
                _action(2, (pack_expression(2, 1, struct.pack("<iB", 2, 1)),)),
                _action(4),
                _action(3, (pack_expression(2, 1, struct.pack("<iB", 2, 0)),)),
            ),
            ("if (true)", "else {", "ElseIf (false)"),
        ),
        (
            (
                _action(2, (pack_expression(2, 1, struct.pack("<iB", 2, 1)),)),
                _action(
                    108,
                    (
                        pack_expression(4, 1, struct.pack("<i", 4) + pack_string("middle")),
                        pack_expression(2, 1, struct.pack("<iB", 2, 1)),
                    ),
                ),
                _action(3, (pack_expression(2, 1, struct.pack("<iB", 2, 0)),)),
            ),
            ("if (true)", 'Notification("middle", true)', "ElseIf (false)"),
        ),
    ),
    ids=("orphan-else", "orphan-elseif", "branch-after-else", "interrupted-branch"),
)
def test_native_branch_records_recover_without_reordering(actions, fragments):
    binary = _module(_trigger("T", actions=actions))
    result = decompile_module(binary, reject_trailing=True)
    for fragment in fragments:
        assert fragment in result.source
    assert compile_source(result.source) == binary


@pytest.mark.parametrize(
    ("action", "code"),
    (
        (_action(2), "ACTION_ARITY"),
        (_action(2, (pack_expression(1, 1, struct.pack("<ii", 1, 1)),)), "ACTION_PARAMETER_TYPE"),
    ),
    ids=("if-missing-condition", "if-int-condition"),
)
def test_malformed_native_branch_recovers_as_raw_and_keeps_its_bytes(action, code):
    binary = _module(_trigger("T", actions=(action,)))
    result = decompile_module(binary, reject_trailing=True)
    assert "raw_action 2" in result.source
    assert encode_module(parse_module(result.source)) == binary
    with pytest.raises(CompileError) as raised:
        compile_source(result.source)
    assert {item.code for item in raised.value.diagnostics} == {code}


def test_unknown_parent_keeps_known_child_readable_and_byte_reversible():
    child = _action(
        108,
        (
            pack_expression(4, 1, struct.pack("<i", 4) + pack_string("child")),
            pack_expression(2, 1, struct.pack("<iB", 2, 1)),
        ),
    )
    binary = _module(_trigger("T", actions=(_action(9001, children=(child,)),)))
    result = decompile_module(binary, reject_trailing=True)
    assert "raw_action 9001()" in result.source
    assert 'Notification("child", true)' in result.source
    assert encode_module(parse_module(result.source)) == binary


def test_shadowed_builtin_name_in_one_trigger_does_not_leak_into_the_next():
    constant_one = pack_expression(1, 1, struct.pack("<ii", 1, 1))
    local_shadow = struct.pack("<i", 1) + pack_string("ThisCard") + constant_one
    builtin_card = pack_expression(1, 10, pack_vector())
    local_read = struct.pack("<i", 1) + pack_string("who") + builtin_card
    binary = _module(
        _trigger("Shadow", variables=(local_shadow,)),
        _trigger("Use builtin", variables=(local_read,)),
    )
    source = decompile_module(binary, reject_trailing=True).source
    assert 'trigger "Shadow"' in source and 'let "ThisCard": int = 1;' in source
    assert 'trigger "Use builtin"' in source and "let who: int = ThisCard;" in source
    assert compile_source(source) == binary


def test_native_loop_and_for_loop_recover_as_readable_control_flow():
    def integer(value):
        return pack_expression(1, 1, struct.pack("<ii", 1, value))

    def boolean(value):
        return pack_expression(2, 1, struct.pack("<iB", 2, value))

    variable = pack_expression(1, 2, pack_string("i"))
    notification = _action(
        108,
        (
            pack_expression(4, 1, struct.pack("<i", 4) + pack_string("for")),
            boolean(1),
        ),
    )
    loop = _action(6, children=(_action(8, (boolean(1),)), _action(7, (boolean(1),))))
    for_loop = _action(
        9,
        (variable, integer(0), integer(2)),
        (notification, _action(8, (boolean(0),)), _action(7, (boolean(1),))),
    )
    local = struct.pack("<i", 1) + pack_string("i") + integer(0)
    binary = _module(_trigger("T", variables=(local,), actions=(loop, for_loop)))

    source = decompile_module(binary, reject_trailing=True).source
    assert "loop {\n      continue;\n      break;\n    }" in source
    assert 'for i from 0 to 2 {\n      Notification("for", true);' in source
    assert "continue if false;\n      break;" in source
    assert compile_source(source) == binary


def test_member_receivers_that_need_quoting_or_parentheses_recover_losslessly():
    def integer(value):
        return pack_expression(1, 1, struct.pack("<ii", 1, value))

    one = integer(1)
    two = integer(2)
    namespace_local = (
        struct.pack("<i", 1) + pack_string("Context") + pack_expression(1, 10, pack_vector())
    )
    namespace_receiver = pack_expression(1, 2, pack_string("Context"))
    computed_receiver = pack_expression(1, 5, pack_vector(one, two))
    actions = (
        _action(13, (namespace_receiver, one, two)),
        _action(13, (one, one, two)),
        _action(13, (computed_receiver, one, two)),
    )
    binary = _module(_trigger("T", variables=(namespace_local,), actions=actions))

    source = decompile_module(binary, reject_trailing=True).source
    assert 'variable("Context").AddLike(1, 2);' in source
    assert "(1).AddLike(1, 2);" in source
    assert "(1 + 2).AddLike(1, 2);" in source
    assert compile_source(source) == binary


def test_nested_unknown_expression_recovers_raw_without_losing_its_wire_tree():
    unknown = pack_expression(1, 9001, pack_vector(pack_expression(1, 1, struct.pack("<ii", 1, 4))))
    local = struct.pack("<i", 1) + pack_string("answer") + unknown
    binary = _module(_trigger("T", variables=(local,)))

    result = decompile_module(binary, reject_trailing=True)
    assert "raw_expression int 9001" in result.source
    assert "raw_expression int 1" not in result.source
    # The fallback warning is folded into the error on the same node.
    (unknown_error,) = result.diagnostics
    assert unknown_error.code == "UNKNOWN_EXPRESSION"
    assert unknown_error.notes
    assert encode_module(parse_module(result.source)) == binary


def test_malformed_member_receiver_recovers_raw_and_preserves_native_bytes():
    boolean = pack_expression(2, 1, struct.pack("<iB", 2, 1))

    def integer(value):
        return pack_expression(1, 1, struct.pack("<ii", 1, value))

    binary = _module(_trigger("T", actions=(_action(13, (boolean, integer(1), integer(2))),)))

    result = decompile_module(binary, reject_trailing=True)
    assert "raw_action 13(true, 1, 2);" in result.source
    assert {item.code for item in result.diagnostics} == {
        "RAW_FALLBACK",
        "ACTION_PARAMETER_TYPE",
    }
    assert encode_module(parse_module(result.source)) == binary


def test_decompile_diagnostics_point_into_recovered_source_once_per_node():
    binary = encode_module(undefined_variables_module())

    result = decompile_module(binary, filename="input", source_filename="out.aa2m")

    assert [(item.code, item.filename, item.line, item.column) for item in result.diagnostics] == [
        ("UNDEFINED_VARIABLE", "out.aa2m", 6, 36),
        ("UNDEFINED_VARIABLE", "out.aa2m", 7, 37),
    ]
    lines = result.source.splitlines()
    for item in result.diagnostics:
        assert lines[item.line - 1][item.column - 1 :].startswith("raw_expression int 2 { variable")
        assert item.offset is not None and item.path[0] == "module"
        assert str(item).startswith(
            f"out.aa2m:{item.line}:{item.column}: warning[UNDEFINED_VARIABLE]"
        )


def _integer(value: int) -> bytes:
    return pack_expression(1, 1, struct.pack("<ii", 1, value))


def _float(value: float) -> bytes:
    return pack_expression(3, 1, struct.pack("<if", 3, value))


def _local(value_type: int, name: str, default: bytes) -> bytes:
    return struct.pack("<i", value_type) + pack_string(name) + default


def _texts(diagnostics) -> str:
    return "\n".join(f"{item.message}\n" + "\n".join(item.notes) for item in diagnostics)


@pytest.mark.parametrize(
    ("variables", "action", "reason"),
    [
        (
            (),
            _action(9, (pack_expression(1, 2, pack_string("j")), _integer(0), _integer(2))),
            "unresolved variable: 'j' is not declared",
        ),
        (
            (_local(3, "f", _float(0.0)),),
            _action(9, (pack_expression(1, 2, pack_string("f")), _integer(0), _integer(2))),
            "declaration mismatch: `for` loop target 'f' must be int, declared float",
        ),
        (
            (_local(1, "i", _integer(0)),),
            _action(9, (pack_expression(1, 2, pack_string("i")), _float(0.0), _integer(2))),
            "declaration mismatch: `for` loop bounds must be int",
        ),
        (
            (),
            _action(1, (pack_expression(1, 2, pack_string("x")), _integer(1))),
            "unresolved variable: 'x' is not declared",
        ),
        (
            (_local(1, "x", _integer(0)),),
            _action(1, (pack_expression(1, 2, pack_string("x")), _float(1.0))),
            "declaration mismatch: assignment target 'x' is int but the target/value types "
            "are int/float",
        ),
    ],
    ids=["for-undeclared", "for-float-target", "for-float-bound", "set-undeclared", "set-type"],
)
def test_malformed_loop_and_assignment_targets_recover_raw_with_their_reason(
    variables, action, reason
):
    binary = _module(_trigger("T", variables=variables, actions=(action,)))

    result = decompile_module(binary, reject_trailing=True)
    identifier = struct.unpack_from("<i", action)[0]
    assert f"raw_action {identifier}" in result.source
    assert reason in _texts(result.diagnostics)
    assert encode_module(parse_module(result.source)) == binary
