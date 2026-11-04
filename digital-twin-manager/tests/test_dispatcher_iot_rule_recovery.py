import copy
from unittest.mock import patch

import pytest

from tests.test_debug_deployment import rule_setup

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.core.all import AllDeployer as CoreDeployer
from deployers.aws.core.dispatcher_iot_rule import DispatcherIotRuleDeployer


@pytest.fixture
def save_rule_plan(rule_setup, monkeypatch, tmp_path):
    monkeypatch.setenv(deployment_state.STATE_DIR_ENV, str(tmp_path / "state"))

    def save(actions):
        deployment_state.save_plan([{
            "group": "core",
            "layers": [
                {"layer": name, "actions": actions if name == "core_l1" else []}
                for name, _ in CoreDeployer.LAYERS
            ],
        }])

    return save


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("replan", [False, True])
def test_failed_permission_after_creation_recovers_with_retry_or_replan(
    rule_setup, save_rule_plan, monkeypatch, debug, replan,
):
    monkeypatch.setattr(globals, "debug", debug)
    rule_setup.rules.rule = None
    rule_setup.lambda_client.permission_statement = None
    save_rule_plan(DispatcherIotRuleDeployer().plan())
    add_permission = rule_setup.lambda_client.add_permission.side_effect
    rule_setup.lambda_client.add_permission.side_effect = ClientError(
        {"Error": {"Code": "TooManyRequestsException"}}, "AddPermission",
    )

    with pytest.raises(ClientError):
        AllDeployer().apply(deployment_state.load_plan())

    assert len(rule_setup.rules.created) == 1
    assert rule_setup.rules.rule is not None
    assert rule_setup.lambda_client.permission_statement is None
    failed_action = deployment_state.load_plan()[0]["layers"][0]["actions"][0]
    assert failed_action["processed"] is False

    rule_setup.lambda_client.add_permission.side_effect = add_permission
    if replan:
        actions = DispatcherIotRuleDeployer().plan()
        assert [action["action"] for action in actions] == ["UPDATE"]
        save_rule_plan(actions)
    AllDeployer().apply(deployment_state.load_plan())

    assert len(rule_setup.rules.created) == 1
    assert rule_setup.rules.replaced == []
    statement = rule_setup.lambda_client.permission_statement
    assert statement["Principal"] == {"Service": "iot.amazonaws.com"}
    assert statement["Condition"]["ArnLike"]["AWS:SourceArn"].endswith(
        "/" + globals.dispatcher_iot_rule_name()
    )
    action = deployment_state.load_plan()[0]["layers"][0]["actions"][0]
    assert action["processed"] is True
    assert DispatcherIotRuleDeployer().plan()[0]["action"] == "NO_CHANGE"


def test_recreating_a_rule_reuses_its_existing_lambda_permission(rule_setup, save_rule_plan):
    original_statement = copy.deepcopy(rule_setup.lambda_client.permission_statement)
    rule_setup.rules.rule = None
    save_rule_plan(DispatcherIotRuleDeployer().plan())

    AllDeployer().apply(deployment_state.load_plan())

    assert len(rule_setup.rules.created) == 1
    rule_setup.lambda_client.add_permission.assert_not_called()
    assert rule_setup.lambda_client.permission_statement == original_statement


def test_missing_permission_and_changed_sql_are_both_repaired(rule_setup, save_rule_plan, monkeypatch):
    monkeypatch.setattr(globals, "debug", True)
    rule_setup.lambda_client.permission_statement = None
    save_rule_plan(DispatcherIotRuleDeployer().plan())

    AllDeployer().apply(deployment_state.load_plan())

    assert len(rule_setup.rules.replaced) == 1
    assert "timestamp() AS iot_ingested_at_ms" in rule_setup.rules.rule["sql"]
    assert rule_setup.lambda_client.permission_statement is not None
    assert DispatcherIotRuleDeployer().plan()[0]["action"] == "NO_CHANGE"


def test_a_conflicting_permission_is_not_replaced(rule_setup):
    rule_setup.lambda_client.permission_statement["Principal"] = {"Service": "s3.amazonaws.com"}
    with pytest.raises(ValueError, match="permission"):
        DispatcherIotRuleDeployer().plan()
    assert rule_setup.rules.created == []
    assert rule_setup.rules.replaced == []
    rule_setup.lambda_client.add_permission.assert_not_called()
    rule_setup.lambda_client.remove_permission.assert_not_called()


def test_permission_removed_after_no_change_plan_blocks_apply(rule_setup, save_rule_plan):
    action, = DispatcherIotRuleDeployer().plan()
    assert action["action"] == "NO_CHANGE"
    save_rule_plan([action])
    rule_setup.lambda_client.permission_statement = None

    with patch.object(AllDeployer, "_apply_group") as apply_group:
        with pytest.raises(ValueError, match="plan"):
            AllDeployer().apply(deployment_state.load_plan())
        apply_group.assert_not_called()


def test_permission_read_failure_is_not_treated_as_a_missing_grant(rule_setup):
    rule_setup.lambda_client.get_policy.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException"}}, "GetPolicy",
    )
    with pytest.raises(PermissionError, match="lambda:GetPolicy"):
        DispatcherIotRuleDeployer().plan()
    rule_setup.lambda_client.add_permission.assert_not_called()


@pytest.mark.parametrize("matching", [False, True])
def test_concurrent_permission_creation_is_accepted_only_for_the_expected_grant(
    rule_setup, save_rule_plan, matching,
):
    statement = copy.deepcopy(rule_setup.lambda_client.permission_statement)
    if not matching:
        statement["Principal"] = {"Service": "s3.amazonaws.com"}
    rule_setup.lambda_client.permission_statement = None
    save_rule_plan(DispatcherIotRuleDeployer().plan())

    def concurrent_add(**request):
        rule_setup.lambda_client.permission_statement = statement
        raise ClientError({"Error": {"Code": "ResourceConflictException"}}, "AddPermission")

    rule_setup.lambda_client.add_permission.side_effect = concurrent_add
    if matching:
        AllDeployer().apply(deployment_state.load_plan())
    else:
        with pytest.raises(ValueError, match="permission"):
            AllDeployer().apply(deployment_state.load_plan())
    rule_setup.lambda_client.remove_permission.assert_not_called()
    assert rule_setup.rules.replaced == []


def test_recovery_rejects_an_unexpected_rule_created_after_planning(rule_setup, save_rule_plan):
    rule_setup.rules.rule = None
    action, = DispatcherIotRuleDeployer().plan()
    save_rule_plan([action])
    rule_setup.rules.rule = copy.deepcopy(action["topic_rule_payload"])
    rule_setup.rules.rule["sql"] = "SELECT * FROM 'unexpected/topic'"

    with patch.object(AllDeployer, "_apply_group") as apply_group:
        with pytest.raises(ValueError, match="plan"):
            AllDeployer().apply(deployment_state.load_plan())
        apply_group.assert_not_called()
    rule_setup.lambda_client.add_permission.assert_not_called()
