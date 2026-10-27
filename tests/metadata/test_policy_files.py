"""Maintainer-facing checks for the shipped language policy."""

from __future__ import annotations

import pytest

from aa2modulus.app.compile import CompileError, compile_source
from aa2modulus.decompile.format.module import format_module
from aa2modulus.metadata.identities import WireIdentity
from aa2modulus.metadata.schema import MetadataError
from tests.support.policy import edited_policy, policy_context
from tests.support.source import parse_module


def test_shipped_default_fills_an_omitted_trailing_argument(context):
    module = parse_module('module "M" { trigger "T" { Notification("ready"); } }', context=context)
    parameter = module.triggers[0].gui_actions[0].action.parameters[1].constant
    assert parameter.value is False


def test_invalid_policy_file_reports_its_path_and_key(tmp_path):
    path = edited_policy(tmp_path, lambda document: document.update(extra_setting=True))
    with pytest.raises(MetadataError) as failure:
        policy_context(path)
    assert str(path) in str(failure.value)
    assert "extra_setting" in str(failure.value)


def test_policy_edit_changes_source_names_and_compiled_default(tmp_path):
    def edit(document):
        document["preferred_names"]["actions"]["108"] = "Notify"
        document["action_defaults"]["108"]["1"] = True

    path = edited_policy(tmp_path, edit)
    context = policy_context(path)
    source = 'module "M" { trigger "T" { Notify("ready"); } }'
    module = parse_module(source, context=context)
    action = module.triggers[0].gui_actions[0].action
    assert action.id == 108
    assert action.parameters[1].constant.value is True
    binary = compile_source(source, context=context)
    formatted = format_module(module, context=context)
    assert 'Notify("ready");' in formatted
    assert compile_source(formatted, context=context) == binary


def test_preferred_name_cannot_take_another_targets_native_name(tmp_path):
    path = edited_policy(
        tmp_path,
        lambda document: document["preferred_names"]["actions"].update({"108": "WriteLog"}),
    )
    with pytest.raises(MetadataError, match="would displace native targets"):
        policy_context(path)


_CARD_RESULTS = {9, 10, 11, 15, 16, 53, 55, 56, 98, 103, 107, 108, 117, 118, 122, 150}


def test_shipped_policy_tags_seat_valued_expressions_as_cards(context):
    policy = context.source_policy
    assert {
        identifier
        for scope, identifier, role in policy.expression_result_roles
        if scope == 1 and role == "card"
    } == _CARD_RESULTS
    assert len(policy.expression_result_roles) == len(_CARD_RESULTS)
    # Rooms are not seats.
    for identifier in (13, 136):
        assert policy.expression_result_role(1, identifier) is None


@pytest.mark.parametrize(
    ("key", "role", "message"),
    [
        ("string:7", "card", "not a member receiver or argument role of type string"),
        ("int:9999", "card", "unknown expression int:9999"),
        ("int:1", "card", "payload markers have no result role"),
        ("int:11", "", "must not be empty"),
    ],
)
def test_result_roles_must_reuse_a_typed_member_role(tmp_path, key, role, message):
    path = edited_policy(
        tmp_path, lambda document: document["result_roles"]["expressions"].update({key: role})
    )
    with pytest.raises(MetadataError, match=message):
        policy_context(path)


@pytest.mark.parametrize(
    ("signature", "message"),
    [
        ("AddLike(towards card, amount: points)", "argument 1 must be 'name: role'"),
        ("AddLike(towards: card)", "2 argument\\(s\\) are required, got 1"),
        ("Add.Like(towards: card, amount: points)", 'write "Name"'),
        ("if(towards: card, amount: points)", "non-keyword source name"),
    ],
)
def test_member_signatures_are_checked(tmp_path, signature, message):
    path = edited_policy(
        tmp_path, lambda document: document["members"]["actions"].update({"13": signature})
    )
    with pytest.raises(MetadataError, match=message):
        policy_context(path)


def test_member_signature_sets_name_and_arguments(tmp_path):
    path = edited_policy(
        tmp_path,
        lambda document: document["members"]["actions"].update(
            {"13": " Befriend ( other : card , by : points ) "}
        ),
    )
    form = policy_context(path).source_policy.member_form_for_target(WireIdentity("action", 13))
    assert form is not None
    assert form.name == "Befriend"
    assert form.receiver_role == "card"
    assert [(item.parameter, item.name, item.role) for item in form.arguments] == [
        (1, "other", "card"),
        (2, "by", "points"),
    ]


def test_result_roles_change_binding_but_not_output(tmp_path, context):
    tagged = (
        'module "M" { trigger "T" { on CARD_ADDED; '
        "Context.NpcAnswerTarget.AddLike(ThisCard, 1); "
        "let t: int = TriggeringCard.Target; } }"
    )
    explicit = (
        'module "M" { trigger "T" { on CARD_ADDED; '
        "Card(Context.NpcAnswerTarget).AddLike(Card(ThisCard), 1); "
        "let t: int = Card(TriggeringCard).Target; } }"
    )
    untagged = policy_context(
        edited_policy(tmp_path, lambda document: document.pop("result_roles"))
    )
    # Without roles the built-in results are plain ints, which are not card receivers.
    with pytest.raises(CompileError, match="expected card, found int"):
        compile_source(tagged, context=untagged)
    assert compile_source(explicit, context=untagged) == compile_source(tagged, context=context)


def test_card_and_int_declarations_compile_to_identical_bytes():
    card = 'module "M" { trigger "T" { on CARD_ADDED; let a: card = ThisCard; a.AddLike(a, 1); } }'
    plain = card.replace("a: card", "a: int").replace(
        "a.AddLike(a, 1)", "Card(a).AddLike(Card(a), 1)"
    )
    assert compile_source(card) == compile_source(plain)


def test_shipped_policy_names_every_flat_parameterized_builtin(context):
    policy, catalog = context.source_policy, context.catalog
    missing = []
    for kind, entries in (
        ("action", context.metadata.actions),
        ("expression", context.metadata.expressions),
    ):
        for entry in entries:
            scope = None if kind == "action" else entry.return_type
            key = WireIdentity(kind, entry.id, scope)
            if (
                not entry.parameter_types
                or policy.member_form_for_target(key) is not None
                or catalog.canonical_name(kind, entry.id, scope) is None
            ):
                continue
            if policy.parameter_names(key) is None:
                missing.append(key)
    assert missing == []


@pytest.mark.parametrize(
    ("section", "key", "names", "message"),
    [
        ("actions", "51", ["pc", "PC"], "must be distinct"),
        ("actions", "51", ["pc", "default"], "not an unqualified non-keyword name"),
        ("actions", "13", ["a", "b", "c"], "written as the member 'AddLike'"),
        ("actions", "9999", ["a"], "unknown action 9999"),
        ("expressions", "int:1", [], "payload markers have no parameters"),
    ],
)
def test_parameter_names_are_validated_against_the_native_target(
    tmp_path, section, key, names, message
):
    path = edited_policy(
        tmp_path, lambda document: document["parameter_names"][section].update({key: names})
    )
    with pytest.raises(MetadataError, match=message):
        policy_context(path)


def test_description_override_loads_and_unknown_targets_fail(tmp_path):
    path = edited_policy(
        tmp_path,
        lambda document: document["descriptions"]["expressions"].update({"int:4": " Curated. "}),
    )
    policy = policy_context(path).source_policy
    assert policy.description_override(WireIdentity("expression", 4, 1)) == "Curated."
    path = edited_policy(
        tmp_path,
        lambda document: document["descriptions"]["expressions"].update({"int:9999": "x"}),
    )
    with pytest.raises(MetadataError, match="unknown expression int:9999"):
        policy_context(path)


@pytest.mark.parametrize(
    ("section", "key", "roles", "message"),
    [
        ("actions", "51", {"other": "card"}, "not a parameter name of action 51"),
        ("actions", "9999", {"seat": "card"}, "unknown action 9999"),
        (
            "expressions",
            "string:24",
            {"text": "card"},
            "not a member receiver or argument role of type string",
        ),
    ],
)
def test_parameter_roles_validate_named_slots_and_native_types(
    tmp_path, section, key, roles, message
):
    path = edited_policy(
        tmp_path,
        lambda document: document["parameter_roles"][section].update({key: roles}),
    )
    with pytest.raises(MetadataError, match=message):
        policy_context(path)


def test_parameter_roles_require_a_parameter_names_entry(tmp_path):
    path = edited_policy(
        tmp_path, lambda document: document["parameter_names"]["actions"].pop("51")
    )
    with pytest.raises(MetadataError, match="has no \\[parameter_names\\] entry"):
        policy_context(path)


def test_parameter_roles_do_not_index_invalid_parameter_names(tmp_path):
    def edit(document):
        document["parameter_names"]["actions"]["51"].append("extra")
        document["parameter_roles"]["actions"]["51"]["extra"] = "card"

    path = edited_policy(tmp_path, edit)
    with pytest.raises(MetadataError, match=r"takes 2 parameter\(s\).*got 3 name\(s\)"):
        policy_context(path)
