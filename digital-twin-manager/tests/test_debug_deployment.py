import copy
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import StubStsClient, install_aws_stubs
from tests.test_managed_lambda_regressions import ManagedLambdaFixture

install_aws_stubs()

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.core.dispatcher_iot_rule import DispatcherIotRuleDeployer
from deployers.aws.core.l1 import L1Deployer
from deployers.aws.core.persister_lambda_function import PersisterLambdaFunctionDeployer


class TopicRules:
    def __init__(self, rule):
        self.meta = SimpleNamespace(region_name="eu-west-1")
        self.rule = rule
        self.rule_name = rule["ruleName"]
        self.created = []
        self.replaced = []
        self.error = None
        self.list_error = None
        self.listed_pages = None
        self.list_requests = []

    def get_topic_rule(self, **request):
        if self.error:
            raise self.error
        if self.rule is None:
            raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetTopicRule")
        return {"rule": copy.deepcopy(self.rule)}

    def create_topic_rule(self, **request):
        self.created.append(copy.deepcopy(request))
        self.rule_name = request["ruleName"]
        self.rule = copy.deepcopy(request["topicRulePayload"])
        self.rule.setdefault("awsIotSqlVersion", "2015-10-08")

    def replace_topic_rule(self, **request):
        self.replaced.append(copy.deepcopy(request))
        self.rule = copy.deepcopy(request["topicRulePayload"])

    def get_paginator(self, operation):
        assert operation == "list_topic_rules"
        self.list_requests.append(operation)

        def pages():
            if self.list_error:
                raise self.list_error
            if self.listed_pages is not None:
                yield from copy.deepcopy(self.listed_pages)
            else:
                yield {"rules": [{"ruleName": self.rule_name}] if self.rule is not None else []}

        return SimpleNamespace(paginate=pages)


@pytest.fixture
def rule_setup(monkeypatch):
    monkeypatch.setattr(globals, "config", {"digital_twin_name": "dt"})
    monkeypatch.setattr(globals, "config_iot_devices", [])
    monkeypatch.setattr(globals, "config_hierarchy", [], raising=False)
    monkeypatch.setattr(deployment_state, "last_applied_config", {"digital_twin_name": "dt"})
    monkeypatch.setattr(globals, "debug", False, raising=False)
    lambda_client = MagicMock()
    lambda_client.meta.region_name = "eu-west-1"
    monkeypatch.setattr(globals, "aws_lambda_client", lambda_client)
    monkeypatch.setattr(globals, "aws_sts_client", StubStsClient())
    topic = globals.dispatcher_iot_rule_topic()
    function = globals.dispatcher_lambda_function_name()
    rules = TopicRules({
        "ruleName": globals.dispatcher_iot_rule_name(),
        "createdAt": "2026-10-01T00:00:00Z",
        "sql": f"SELECT * FROM '{topic}'",
        "description": "Keep this description",
        "actions": [{"lambda": {"functionArn": f"arn:aws:lambda:eu-west-1:123456789012:function:{function}"}}],
        "ruleDisabled": False,
        "awsIotSqlVersion": "2016-03-23",
        "errorAction": {"lambda": {"functionArn": "arn:aws:lambda:eu-west-1:123456789012:function:errors"}},
    })
    monkeypatch.setattr(globals, "aws_iot_client", rules)
    lambda_client.permission_statement = {
        "Sid": "iot-invoke",
        "Effect": "Allow",
        "Principal": {"Service": "iot.amazonaws.com"},
        "Action": "lambda:InvokeFunction",
        "Resource": rules.rule["actions"][0]["lambda"]["functionArn"],
        "Condition": {"ArnLike": {
            "AWS:SourceArn": f"arn:aws:iot:eu-west-1:123456789012:rule/{globals.dispatcher_iot_rule_name()}",
        }},
    }

    def get_policy(**request):
        if lambda_client.permission_statement is None:
            raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetPolicy")
        return {"Policy": json.dumps({"Statement": [lambda_client.permission_statement]})}

    def add_permission(**request):
        if lambda_client.permission_statement is not None:
            raise ClientError({"Error": {"Code": "ResourceConflictException"}}, "AddPermission")
        lambda_client.permission_statement = {
            "Sid": request["StatementId"],
            "Effect": "Allow",
            "Principal": {"Service": request["Principal"]},
            "Action": request["Action"],
            "Resource": f"arn:aws:lambda:eu-west-1:123456789012:function:{request['FunctionName']}",
            "Condition": {"ArnLike": {"AWS:SourceArn": request["SourceArn"]}},
        }
        return {"Statement": json.dumps(lambda_client.permission_statement)}

    lambda_client.get_policy.side_effect = get_policy
    lambda_client.add_permission.side_effect = add_permission
    return SimpleNamespace(rules=rules, lambda_client=lambda_client, topic=topic)


@pytest.mark.parametrize("value, expected", [
    (None, False), ("False", False), ("invalid", False),
    ("True", True), ("true", True), ("TRUE", True), (" true ", True),
])
def test_debug_environment_is_opt_in(monkeypatch, value, expected):
    monkeypatch.delenv("DEBUG", raising=False)
    if value is not None:
        monkeypatch.setenv("DEBUG", value)
    with patch("dotenv.load_dotenv"):
        configuration = runpy.run_path(str(REPO_ROOT / "src/globals.py"))
    assert configuration["debug"] is expected


@pytest.mark.parametrize("debug", [False, True])
def test_persister_receives_debug_environment(rule_setup, monkeypatch, debug):
    monkeypatch.setattr(globals, "debug", debug)
    environment = PersisterLambdaFunctionDeployer()._lambda_definition().environment
    assert environment["DEBUG"].lower() == str(debug).lower()


def expected_sql(topic, debug):
    fields = "*, timestamp() AS iot_ingested_at_ms" if debug else "*"
    return f"SELECT {fields} FROM '{topic}'"


@pytest.mark.parametrize("debug", [False, True])
def test_new_iot_rule_selects_timestamp_only_in_debug(rule_setup, monkeypatch, debug):
    monkeypatch.setattr(globals, "debug", debug)
    rule_setup.rules.rule = None
    DispatcherIotRuleDeployer().deploy()
    payload = rule_setup.rules.created[0]["topicRulePayload"]
    assert payload["sql"] == expected_sql(rule_setup.topic, debug)


@pytest.mark.parametrize("debug", [False, True])
def test_debug_toggle_updates_existing_rule_without_recreation(rule_setup, monkeypatch, debug):
    rule_setup.rules.rule["sql"] = expected_sql(rule_setup.topic, not debug)
    previous = copy.deepcopy(rule_setup.rules.rule)
    monkeypatch.setattr(globals, "debug", debug)
    actions = DispatcherIotRuleDeployer().plan()
    assert [action["action"] for action in actions] == ["UPDATE"]

    with patch("deployment_state.mark_plan_action_processed") as mark_processed:
        L1Deployer().apply({"layer": "core_l1", "actions": actions}, "DEPLOY")

    assert rule_setup.rules.created == []
    assert len(rule_setup.rules.replaced) == 1
    payload = rule_setup.rules.replaced[0]["topicRulePayload"]
    assert payload["sql"] == expected_sql(rule_setup.topic, debug)
    for field in ("description", "errorAction", "awsIotSqlVersion", "actions"):
        assert payload[field] == previous[field]
    assert "ruleName" not in payload
    assert "createdAt" not in payload
    rule_setup.lambda_client.add_permission.assert_not_called()
    mark_processed.assert_called_once()
    assert DispatcherIotRuleDeployer().plan()[0]["action"] == "NO_CHANGE"


@pytest.mark.parametrize("debug", [False, True])
def test_matching_debug_rule_needs_no_change(rule_setup, monkeypatch, debug):
    monkeypatch.setattr(globals, "debug", debug)
    rule_setup.rules.rule["sql"] = expected_sql(rule_setup.topic, debug)
    assert DispatcherIotRuleDeployer().plan()[0]["action"] == "NO_CHANGE"


def test_missing_rule_is_deployed_with_debug_enabled(rule_setup, monkeypatch):
    monkeypatch.setattr(globals, "debug", True)
    rule_setup.rules.rule = None
    action, = DispatcherIotRuleDeployer().plan()
    assert action["action"] == "DEPLOY"
    DispatcherIotRuleDeployer().apply(action, action["resource"])
    assert rule_setup.rules.created[0]["topicRulePayload"]["sql"] == expected_sql(rule_setup.topic, True)


def test_rule_lookup_failure_does_not_plan_creation(rule_setup):
    rule_setup.rules.error = ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetTopicRule")
    with pytest.raises(ClientError):
        DispatcherIotRuleDeployer().plan()


@pytest.mark.parametrize("initial_debug", [False, True])
def test_debug_change_after_plan_is_rejected_before_apply(rule_setup, monkeypatch, initial_debug):
    monkeypatch.setattr(globals, "debug", initial_debug)
    actions = DispatcherIotRuleDeployer().plan()
    monkeypatch.setattr(globals, "debug", not initial_debug)
    group = {"group": "core", "layers": [{"layer": "core_l1", "actions": actions}]}
    with patch.object(AllDeployer, "_apply_group") as apply_group:
        with pytest.raises(ValueError, match="plan"):
            AllDeployer().apply([group])
        apply_group.assert_not_called()
    assert rule_setup.rules.replaced == []


@pytest.mark.parametrize("field", ["topic_rule_payload", "aws_topic_rule_payload"])
def test_saved_plan_without_rule_metadata_is_rejected(rule_setup, monkeypatch, field):
    monkeypatch.setattr(globals, "debug", True)
    action, = DispatcherIotRuleDeployer().plan()
    del action[field]
    with pytest.raises(ValueError, match="metadata"):
        DispatcherIotRuleDeployer().apply(action, action["resource"])
    assert rule_setup.rules.replaced == []


class DebugLambdaUpdateTests(ManagedLambdaFixture):
    def test_debug_toggle_updates_persister_environment_and_preserves_arn(self):
        with patch.object(globals, "debug", False):
            deployer, name = self.deploy_core(PersisterLambdaFunctionDeployer)
        original_arn = self.lambda_client.functions[name]["FunctionArn"]
        create_count = len(self.lambda_client.create_requests)
        for enabled in (True, False):
            with self.subTest(debug=enabled), patch.object(globals, "debug", enabled):
                action = self.single_action(deployer.plan(), "UPDATE")
                deployer.apply(action, name)
                environment = self.lambda_client.functions[name]["Environment"]["Variables"]
                self.assertEqual(str(enabled), environment["DEBUG"])
                self.assert_updated_without_replacement(name, original_arn, create_count)
                self.single_action(deployer.plan(), "NO_CHANGE")

    def test_debug_change_after_persister_plan_rejects_all_apply(self):
        with patch.object(globals, "debug", False):
            deployer, _ = self.deploy_core(PersisterLambdaFunctionDeployer)
            plan = self.plan_for_group("core", "core_l2", deployer.plan())
        with patch.object(globals, "debug", True):
            self.assert_rejected_before_any_group(plan)


def test_aws_rule_change_after_plan_is_rejected(rule_setup, monkeypatch):
    monkeypatch.setattr(globals, "debug", True)
    action, = DispatcherIotRuleDeployer().plan()
    rule_setup.rules.rule["description"] = "Changed after planning"
    with pytest.raises(ValueError, match="plan"):
        DispatcherIotRuleDeployer().apply(action, action["resource"])
    assert rule_setup.rules.replaced == []
