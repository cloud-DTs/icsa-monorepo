import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.test_debug_deployment import rule_setup
from tests.test_dispatcher_iot_rule_recovery import save_rule_plan

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.core.dispatcher_iot_rule import DispatcherIotRuleDeployer


@pytest.fixture
def same_name_replacement(rule_setup, monkeypatch):
    monkeypatch.setattr(deployment_state, "last_applied_config", {"digital_twin_name": "dt-a"})
    monkeypatch.setattr(globals, "config", {"digital_twin_name": "dt_a"})
    old_function = deployment_state.last_applied_dispatcher_lambda_function_name()
    rule_name = deployment_state.last_applied_dispatcher_iot_rule_name()
    assert rule_name == globals.dispatcher_iot_rule_name()
    rule_setup.rules.rule_name = rule_name
    rule_setup.rules.rule.update({
        "ruleName": rule_name,
        "sql": f"SELECT * FROM '{deployment_state.last_applied_dispatcher_iot_rule_topic()}'",
        "actions": [{"lambda": {
            "functionArn": f"arn:aws:lambda:eu-west-1:123456789012:function:{old_function}",
        }}],
    })
    statement = copy.deepcopy(rule_setup.lambda_client.permission_statement)
    statement["Resource"] = rule_setup.rules.rule["actions"][0]["lambda"]["functionArn"]
    statement["Condition"]["ArnLike"]["AWS:SourceArn"] = (
        f"arn:aws:iot:eu-west-1:123456789012:rule/{rule_name}"
    )
    permissions = {old_function: statement}
    deleted = []

    class MissingPermission(ClientError):
        pass

    rule_setup.lambda_client.exceptions = SimpleNamespace(ResourceNotFoundException=MissingPermission)

    def get_policy(**request):
        grant = permissions.get(request["FunctionName"])
        if grant is None:
            raise MissingPermission({"Error": {"Code": "ResourceNotFoundException"}}, "GetPolicy")
        return {"Policy": json.dumps({"Statement": [grant]})}

    def add_permission(**request):
        assert request["FunctionName"] not in permissions
        permissions[request["FunctionName"]] = {
            "Sid": request["StatementId"],
            "Effect": "Allow",
            "Principal": {"Service": request["Principal"]},
            "Action": request["Action"],
            "Resource": f"arn:aws:lambda:eu-west-1:123456789012:function:{request['FunctionName']}",
            "Condition": {"ArnLike": {"AWS:SourceArn": request["SourceArn"]}},
        }

    def remove_permission(**request):
        if permissions.pop(request["FunctionName"], None) is None:
            raise MissingPermission({"Error": {"Code": "ResourceNotFoundException"}}, "RemovePermission")

    def delete_topic_rule(**request):
        deleted.append(request["ruleName"])
        rule_setup.rules.rule = None

    rule_setup.lambda_client.get_policy.side_effect = get_policy
    rule_setup.lambda_client.add_permission.side_effect = add_permission
    rule_setup.lambda_client.remove_permission.side_effect = remove_permission
    monkeypatch.setattr(rule_setup.rules, "delete_topic_rule", delete_topic_rule, raising=False)
    return SimpleNamespace(permissions=permissions, deleted=deleted, old_function=old_function)


@pytest.mark.parametrize("debug", [False, True])
def test_apply_replaces_a_rule_with_the_same_name(
    rule_setup, same_name_replacement, save_rule_plan, monkeypatch, debug,
):
    monkeypatch.setattr(globals, "debug", debug)
    actions = DispatcherIotRuleDeployer().plan()
    assert [action["action"] for action in actions] == ["DESTROY", "DEPLOY"]
    save_rule_plan(actions)

    AllDeployer().apply(deployment_state.load_plan())

    assert same_name_replacement.deleted == [globals.dispatcher_iot_rule_name()]
    assert len(rule_setup.rules.created) == 1
    assert rule_setup.rules.rule["sql"] == actions[1]["topic_rule_payload"]["sql"]
    assert rule_setup.rules.rule["actions"] == actions[1]["topic_rule_payload"]["actions"]
    assert same_name_replacement.old_function not in same_name_replacement.permissions
    assert globals.dispatcher_lambda_function_name() in same_name_replacement.permissions
    assert all(action["processed"] for action in deployment_state.load_plan()[0]["layers"][0]["actions"])


@pytest.mark.parametrize("failure_point", ["create", "permission"])
def test_replacement_can_resume_after_destroying_the_old_rule(
    rule_setup, same_name_replacement, save_rule_plan, monkeypatch, failure_point,
):
    actions = DispatcherIotRuleDeployer().plan()
    save_rule_plan(actions)
    error = ClientError({"Error": {"Code": "ServiceUnavailableException"}}, "Replacement")
    if failure_point == "create":
        original_create = rule_setup.rules.create_topic_rule

        def fail_create(**request):
            raise error

        monkeypatch.setattr(rule_setup.rules, "create_topic_rule", fail_create)
    else:
        original_add = rule_setup.lambda_client.add_permission.side_effect
        rule_setup.lambda_client.add_permission.side_effect = error

    with pytest.raises(ClientError) as raised:
        AllDeployer().apply(deployment_state.load_plan())
    assert raised.value is error
    saved_actions = deployment_state.load_plan()[0]["layers"][0]["actions"]
    assert [action["processed"] for action in saved_actions] == [True, False]

    if failure_point == "create":
        monkeypatch.setattr(rule_setup.rules, "create_topic_rule", original_create)
    else:
        rule_setup.lambda_client.add_permission.side_effect = original_add
    AllDeployer().apply(deployment_state.load_plan())

    assert same_name_replacement.deleted == [globals.dispatcher_iot_rule_name()]
    assert len(rule_setup.rules.created) == 1
    assert globals.dispatcher_lambda_function_name() in same_name_replacement.permissions


@pytest.mark.parametrize("destroy_state", ["pending", "missing", "blocked", "processed"])
def test_replacement_does_not_delete_an_unexpected_or_unapproved_rule(
    rule_setup, same_name_replacement, save_rule_plan, destroy_state,
):
    actions = DispatcherIotRuleDeployer().plan()
    if destroy_state == "pending":
        rule_setup.rules.rule["description"] = "Changed after planning"
    elif destroy_state == "missing":
        actions = actions[1:]
    else:
        actions[0][destroy_state] = True
    save_rule_plan(actions)

    with patch.object(AllDeployer, "_apply_group") as apply_group:
        with pytest.raises(ValueError, match="plan"):
            AllDeployer().apply(deployment_state.load_plan())
        apply_group.assert_not_called()
    assert same_name_replacement.deleted == []
    rule_setup.lambda_client.remove_permission.assert_not_called()


def test_replacement_rechecks_the_old_rule_immediately_before_deletion(
    rule_setup, same_name_replacement, save_rule_plan,
):
    save_rule_plan(DispatcherIotRuleDeployer().plan())
    apply_group = AllDeployer._apply_group

    def change_before_destroy(deployer, group, phase):
        if phase == "DESTROY":
            rule_setup.rules.rule["description"] = "Changed after preflight"
        return apply_group(deployer, group, phase)

    with patch.object(AllDeployer, "_apply_group", change_before_destroy):
        with pytest.raises(ValueError, match="plan"):
            AllDeployer().apply(deployment_state.load_plan())
    assert same_name_replacement.deleted == []
    rule_setup.lambda_client.remove_permission.assert_not_called()


def test_replacement_can_resume_if_deletion_finished_before_recording_completion(
    rule_setup, same_name_replacement, save_rule_plan,
):
    save_rule_plan(DispatcherIotRuleDeployer().plan())
    with patch("deployment_state.mark_plan_action_processed", side_effect=RuntimeError("State write failed")):
        with pytest.raises(RuntimeError, match="State write"):
            AllDeployer().apply(deployment_state.load_plan())

    assert rule_setup.rules.rule is None
    AllDeployer().apply(deployment_state.load_plan())

    assert same_name_replacement.deleted == [globals.dispatcher_iot_rule_name()]
    assert len(rule_setup.rules.created) == 1
    assert globals.dispatcher_lambda_function_name() in same_name_replacement.permissions


def test_replacement_cannot_create_before_the_old_rule_is_deleted(
    rule_setup, same_name_replacement,
):
    _, deploy_action = DispatcherIotRuleDeployer().plan()
    with pytest.raises(ValueError, match="plan"):
        DispatcherIotRuleDeployer().apply(deploy_action, deploy_action["resource"])
    assert rule_setup.rules.created == []
    rule_setup.lambda_client.add_permission.assert_not_called()


@pytest.mark.parametrize("missing_before_plan", [False, True])
def test_replacement_handles_an_already_missing_old_rule(
    rule_setup, same_name_replacement, save_rule_plan, missing_before_plan,
):
    if missing_before_plan:
        rule_setup.rules.rule = None
    save_rule_plan(DispatcherIotRuleDeployer().plan())
    rule_setup.rules.rule = None

    AllDeployer().apply(deployment_state.load_plan())

    assert same_name_replacement.deleted == []
    assert len(rule_setup.rules.created) == 1
    assert globals.dispatcher_lambda_function_name() in same_name_replacement.permissions


def test_old_replacement_plan_requires_a_snapshot_before_deleting_the_rule(
    rule_setup, same_name_replacement, save_rule_plan,
):
    actions = DispatcherIotRuleDeployer().plan()
    actions[0].pop("aws_topic_rule_payload", None)
    save_rule_plan(actions)

    with patch.object(AllDeployer, "_apply_group") as apply_group:
        with pytest.raises(ValueError, match="metadata"):
            AllDeployer().apply(deployment_state.load_plan())
        apply_group.assert_not_called()
    assert same_name_replacement.deleted == []


@pytest.mark.parametrize("code", ["UnauthorizedException", "AccessDeniedException"])
def test_replacement_planning_stops_when_the_old_rule_cannot_be_read(
    rule_setup, same_name_replacement, code,
):
    error = ClientError({"Error": {"Code": code}}, "GetTopicRule")
    rule_setup.rules.error = error

    with pytest.raises(ClientError) as raised:
        DispatcherIotRuleDeployer().plan()

    assert raised.value is error
    assert same_name_replacement.deleted == []
    rule_setup.lambda_client.remove_permission.assert_not_called()


def test_replacement_rejects_an_unexpected_rule_appearing_after_deletion(
    rule_setup, same_name_replacement, save_rule_plan,
):
    save_rule_plan(DispatcherIotRuleDeployer().plan())
    apply_group = AllDeployer._apply_group

    def create_foreign_rule(deployer, group, phase):
        if phase == "DEPLOY":
            rule_setup.rules.rule = {"sql": "SELECT * FROM 'unexpected/topic'"}
        return apply_group(deployer, group, phase)

    with patch.object(AllDeployer, "_apply_group", create_foreign_rule):
        with pytest.raises(ValueError, match="plan"):
            AllDeployer().apply(deployment_state.load_plan())

    assert same_name_replacement.deleted == [globals.dispatcher_iot_rule_name()]
    assert rule_setup.rules.created == []
    assert rule_setup.rules.rule == {"sql": "SELECT * FROM 'unexpected/topic'"}
    rule_setup.lambda_client.add_permission.assert_not_called()
