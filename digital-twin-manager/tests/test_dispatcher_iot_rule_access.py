import copy
from unittest.mock import patch

import pytest

from tests.test_debug_deployment import rule_setup
from tests.test_dispatcher_iot_rule_recovery import save_rule_plan

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.core.dispatcher_iot_rule import DispatcherIotRuleDeployer


def denied_rule_read(rule_setup, code="UnauthorizedException"):
    error = ClientError({"Error": {"Code": code}}, "GetTopicRule")
    rule_setup.rules.error = error
    return error


@pytest.mark.parametrize("code", ["UnauthorizedException", "AccessDeniedException", "ServiceUnavailableException"])
def test_unreadable_existing_rule_cannot_produce_a_creation_plan(rule_setup, code):
    error = denied_rule_read(rule_setup, code)
    with pytest.raises(ClientError) as raised:
        DispatcherIotRuleDeployer().plan()
    assert raised.value is error
    assert rule_setup.rules.created == []
    rule_setup.lambda_client.add_permission.assert_not_called()


@pytest.mark.parametrize("planned_action", ["DEPLOY", "UPDATE", "NO_CHANGE"])
@pytest.mark.parametrize("code", ["UnauthorizedException", "AccessDeniedException"])
def test_unreadable_rule_blocks_apply_before_any_group_changes(
    rule_setup, save_rule_plan, monkeypatch, planned_action, code,
):
    if planned_action == "DEPLOY":
        rule_setup.rules.rule = None
    elif planned_action == "UPDATE":
        monkeypatch.setattr(globals, "debug", True)
    action, = DispatcherIotRuleDeployer().plan()
    assert action["action"] == planned_action
    save_rule_plan([action])
    if planned_action == "DEPLOY":
        rule_setup.rules.rule = copy.deepcopy(action["topic_rule_payload"])
    error = denied_rule_read(rule_setup, code)

    with patch.object(AllDeployer, "_apply_group") as apply_group:
        with pytest.raises(ClientError) as raised:
            AllDeployer().apply(deployment_state.load_plan())
        assert raised.value is error
        apply_group.assert_not_called()
    assert rule_setup.rules.created == []
    assert rule_setup.rules.replaced == []
    rule_setup.lambda_client.add_permission.assert_not_called()


def test_direct_deploy_stops_when_an_existing_rule_is_unreadable(rule_setup):
    error = denied_rule_read(rule_setup)
    with pytest.raises(ClientError) as raised:
        DispatcherIotRuleDeployer().deploy()
    assert raised.value is error
    assert rule_setup.rules.created == []
    rule_setup.lambda_client.add_permission.assert_not_called()


def test_info_does_not_report_an_unreadable_rule_as_missing(rule_setup, capsys):
    error = denied_rule_read(rule_setup)
    with pytest.raises(ClientError) as raised:
        DispatcherIotRuleDeployer().info()
    assert raised.value is error
    assert "missing" not in capsys.readouterr().out


def test_complete_rule_listing_can_confirm_absence_after_unauthorized_read(rule_setup):
    rule_setup.rules.rule = None
    denied_rule_read(rule_setup)
    rule_setup.rules.listed_pages = [
        {"rules": [{"ruleName": "other-rule"}]},
        {"rules": []},
    ]
    action, = DispatcherIotRuleDeployer().plan()
    assert action["action"] == "DEPLOY"
    assert rule_setup.rules.list_requests == ["list_topic_rules"]


def test_rule_on_a_later_listing_page_is_not_treated_as_missing(rule_setup):
    error = denied_rule_read(rule_setup)
    rule_setup.rules.listed_pages = [
        {"rules": [{"ruleName": "other-rule"}]},
        {"rules": [{"ruleName": globals.dispatcher_iot_rule_name()}]},
    ]
    with pytest.raises(ClientError) as raised:
        DispatcherIotRuleDeployer().plan()
    assert raised.value is error
    assert rule_setup.rules.list_requests == ["list_topic_rules"]


@pytest.mark.parametrize("code", ["UnauthorizedException", "ServiceUnavailableException"])
def test_failed_listing_cannot_confirm_rule_absence(rule_setup, code):
    rule_setup.rules.rule = None
    denied_rule_read(rule_setup)
    error = ClientError({"Error": {"Code": code}}, "ListTopicRules")
    rule_setup.rules.list_error = error
    with pytest.raises(ClientError) as raised:
        DispatcherIotRuleDeployer().plan()
    assert raised.value is error
    assert rule_setup.rules.created == []


def test_info_reports_missing_only_after_confirming_absence(rule_setup, capsys):
    rule_setup.rules.rule = None
    denied_rule_read(rule_setup)
    DispatcherIotRuleDeployer().info()
    assert "missing" in capsys.readouterr().out
    assert rule_setup.rules.list_requests == ["list_topic_rules"]
