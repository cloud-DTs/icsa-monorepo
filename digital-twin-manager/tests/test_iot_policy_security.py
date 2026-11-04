import copy
import fnmatch
import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_shared_iot_policy import StatefulIotClient

import deployment_state
import globals
from deployers.aws.iot.iot_policy import IotPolicyDeployer


@pytest.fixture
def policy_environment(monkeypatch):
  client = StatefulIotClient()
  monkeypatch.setattr(globals, "aws_iot_client", client)
  monkeypatch.setattr(globals, "aws_sts_client", SimpleNamespace(get_caller_identity=lambda: {"Account": "123456789012"}))
  monkeypatch.setattr(globals, "config", {"digital_twin_name": "MGridICSA"})
  monkeypatch.setattr(globals, "config_events", [], raising=False)
  monkeypatch.setattr(globals, "config_iot_devices", [{"id": "sensor-a"}], raising=False)
  monkeypatch.setattr(deployment_state, "last_applied_config", {"digital_twin_name": "MGridICSA"})
  monkeypatch.setattr(deployment_state, "last_applied_config_events", [], raising=False)
  return client


def allowed(document, action, resource, *, thing="MGridICSA-sensor-a", attached=True):
  """Evaluate the documented subset used by this policy, independently of its builder."""
  context = {"iot:Connection.Thing.ThingName": thing, "iot:Connection.Thing.IsAttached": str(attached).lower()}
  grants = []
  for statement in document["Statement"]:
    actions = statement["Action"]
    resources = statement["Resource"]
    actions = [actions] if isinstance(actions, str) else actions
    resources = [resources] if isinstance(resources, str) else resources
    matches = any(fnmatch.fnmatchcase(action, pattern) for pattern in actions)
    expanded = [value.replace("${iot:Connection.Thing.ThingName}", thing) for value in resources]
    matches = matches and any(fnmatch.fnmatchcase(resource, pattern) for pattern in expanded)
    for operator, conditions in statement.get("Condition", {}).items():
      for key, expected in conditions.items():
        actual = context.get(key, "")
        if operator == "Bool":
          matches = matches and actual == str(expected).lower()
        elif operator == "StringLike":
          matches = matches and fnmatch.fnmatchcase(actual, expected)
        else:
          raise AssertionError("Unsupported test policy condition: " + operator)
    if matches:
      grants.append(statement["Effect"])
  return "Allow" in grants and "Deny" not in grants


def created_document(client):
  IotPolicyDeployer().deploy()
  return client.policies["MGridICSA-iot-policy"]


def test_generated_policy_closes_both_reported_wildcard_findings(policy_environment):
  document = created_document(policy_environment)
  for statement in document["Statement"]:
    for field in ("Action", "Resource"):
      values = statement[field]
      values = [values] if isinstance(values, str) else values
      assert all("*" not in value and "?" not in value for value in values)


def test_valid_device_can_connect_and_publish_telemetry(policy_environment):
  document = created_document(policy_environment)
  prefix = "arn:aws:iot:eu-west-1:123456789012:"
  assert allowed(document, "iot:Connect", prefix + "client/MGridICSA-sensor-a")
  assert allowed(document, "iot:Publish", prefix + "topic/MGridICSA/iot-data")


@pytest.mark.parametrize("action,resource,context", [
  ("iot:Connect", "client/MGridICSA-sensor-b", {}),
  ("iot:Connect", "client/sensor-a", {}),
  ("iot:Connect", "client/OtherTwin-sensor-a", {"thing": "OtherTwin-sensor-a"}),
  ("iot:Connect", "client/MGridICSA-sensor-a", {"attached": False}),
  ("iot:Publish", "topic/OtherTwin/iot-data", {}),
  ("iot:Publish", "topic/MGridICSA/iot-data/extra", {}),
  ("iot:Publish", "topic/$aws/things/MGridICSA-sensor-b/shadow/update", {}),
  ("iot:Publish", "topic/MGridICSA/iot-data", {"attached": False}),
  ("iot:Subscribe", "topicfilter/MGridICSA/iot-data", {}),
  ("iot:UpdateThingShadow", "thing/MGridICSA-sensor-a", {}),
])
def test_unrelated_clients_topics_and_operations_are_denied(policy_environment, action, resource, context):
  document = created_document(policy_environment)
  assert not allowed(document, action, "arn:aws:iot:eu-west-1:123456789012:" + resource, **context)


def test_configured_feedback_keeps_exact_custom_and_own_device_topics(policy_environment):
  globals.config_events = [
    {"action": {"feedback": {"type": "mqtt", "topic": "MGridICSA/commands"}}},
    {"action": {"feedback": {"type": "mqtt", "iotDeviceId": "sensor-a"}}},
  ]
  document = created_document(policy_environment)
  prefix = "arn:aws:iot:eu-west-1:123456789012:"
  for action, kind in (("iot:Subscribe", "topicfilter/"), ("iot:Receive", "topic/")):
    assert allowed(document, action, prefix + kind + "MGridICSA/commands")
    assert allowed(document, action, prefix + kind + "MGridICSA-sensor-a")
    assert not allowed(document, action, prefix + kind + "MGridICSA-sensor-b")
    assert not allowed(document, action, prefix + kind + "MGridICSA/commands/extra")
    assert not allowed(document, action, prefix + kind + "OtherTwin/commands")
  assert not allowed(document, "iot:Publish", prefix + "topic/MGridICSA/commands")


@pytest.mark.parametrize("topic", ["commands/*", "commands/?", "${iot:ClientId}", "commands/#", "commands/+", "bad topic"])
def test_custom_feedback_cannot_inject_policy_patterns(policy_environment, topic):
  globals.config_events = [{"action": {"feedback": {"type": "mqtt", "topic": topic}}}]
  with pytest.raises(ValueError, match="topic"):
    IotPolicyDeployer().plan()
  assert policy_environment.mutations == []


def test_policy_size_does_not_grow_with_household_count(policy_environment):
  first = copy.deepcopy(created_document(policy_environment))
  globals.config_iot_devices = [{"id": f"device-{i}"} for i in range(2001)]
  assert IotPolicyDeployer()._desired_policy_document() == first
  assert len(json.dumps(first, separators=(",", ":"))) <= 2048


def test_too_many_custom_feedback_topics_fail_before_mutating_aws(policy_environment):
  globals.config_events = [
    {"action": {"feedback": {"type": "mqtt", "topic": "MGridICSA/commands/" + str(index) + "a" * 100}}}
    for index in range(20)
  ]
  with pytest.raises(ValueError, match="2048"):
    IotPolicyDeployer().plan()
  assert policy_environment.mutations == []


def test_actual_security_audit_reports_two_legacy_highs_and_none_for_scoped_policy(policy_environment):
  path = Path(__file__).resolve().parents[1] / "scripts/security_audit.py"
  spec = importlib.util.spec_from_file_location("audit_iot_policy_test", path)
  audit = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(audit)

  class Client:
    def get_paginator(self, operation):
      pages = {
        "list_policies": {"policies": [{"policyName": "MGridICSA-iot-policy"}]},
        "list_things": {"things": []},
        "list_topic_rules": {"rules": []},
      }
      return SimpleNamespace(paginate=lambda: [pages[operation]])

    def get_policy(self, policyName):
      return policy_environment.get_policy(policyName=policyName)

  session = SimpleNamespace(client=lambda service: Client())
  from tests.test_shared_iot_policy import POLICY_DOCUMENT
  policy_environment.create_policy(policyName="MGridICSA-iot-policy", policyDocument=json.dumps(POLICY_DOCUMENT))
  assert len([f for f in audit.iot_findings(session, "MGridICSA") if f["severity"] == "High"]) == 2
  IotPolicyDeployer().deploy()
  assert audit.iot_findings(session, "MGridICSA") == []
