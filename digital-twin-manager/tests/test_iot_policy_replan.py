import copy
import json
from pathlib import Path

import pytest

from tests.test_iot_policy_security import policy_environment

import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.iot.all import AllDeployer as IotDeployer
from deployers.aws.iot.iot_policy import IotPolicyDeployer
from deployers.aws.iot.l1 import L1Deployer


NAME = "MGridICSA-iot-policy"


def feedback(topic):
  return [{"action": {"feedback": {"type": "mqtt", "topic": topic}}}]


def policy_action(plan):
  return next(
    action
    for group in plan if group["group"] == "iot"
    for layer in group["layers"] if layer["layer"] == "iot_l1"
    for action in layer["actions"] if action["resource_type"] == "iot_policy"
  )


@pytest.fixture
def pending_policy_update(policy_environment, monkeypatch, tmp_path):
  client = policy_environment
  monkeypatch.setenv(deployment_state.STATE_DIR_ENV, str(tmp_path / "state"))
  monkeypatch.setenv(globals.CONFIG_DIR_ENV, str(tmp_path / "configs"))
  monkeypatch.setattr(globals, "config_iot_devices", [])
  monkeypatch.setattr(globals, "config_hierarchy", {}, raising=False)
  monkeypatch.setattr(globals, "config_credentials", {"aws_region": client.meta.region_name})
  monkeypatch.setattr(deployment_state, "last_applied_config_iot_devices", [])
  monkeypatch.setattr(deployment_state, "last_applied_config_hierarchy", {})
  monkeypatch.setattr(deployment_state, "last_applied_state_metadata", {})
  globals.config_events = feedback("commands/A")
  configs = {
    "config.json": globals.config,
    "config_events.json": globals.config_events,
    "config_iot_devices.json": [],
    "config_hierarchy.json": {},
  }
  (tmp_path / "configs").mkdir()
  for name, value in configs.items():
    (tmp_path / "configs" / name).write_text(json.dumps(value), encoding="utf-8")
  deployment_state.save_last_applied_config_state()
  IotPolicyDeployer().deploy()
  client.attachments["certificate-a"] = {NAME}

  class LaterGroup:
    fail = True

    def plan(self):
      return {"group": "later", "layers": []}

    def apply(self, group_plan, phase):
      if phase == "DEPLOY" and self.fail:
        raise RuntimeError("Later group failed")

  monkeypatch.setattr(IotDeployer, "LAYERS", [("iot_l1", L1Deployer)])
  monkeypatch.setattr(AllDeployer, "GROUP_DEPLOYERS", {"iot": IotDeployer, "later": LaterGroup})
  globals.config_events = feedback("commands/B")
  plan = AllDeployer().plan()
  assert policy_action(plan)["action"] == "UPDATE"
  deployment_state.save_plan(plan)
  client.mutations.clear()
  return client, LaterGroup


def apply_until_later_group_fails():
  with pytest.raises(RuntimeError, match="Later group failed"):
    AllDeployer().apply(deployment_state.load_plan())


def test_replan_preserves_partial_apply_ownership_after_replacing_the_saved_plan(
  pending_policy_update,
):
  client, later_group = pending_policy_update
  apply_until_later_group_fails()
  applied = policy_action(deployment_state.load_plan())
  assert applied["processed"]
  assert client.policies[NAME] == applied["policy_document"]
  assert deployment_state.last_applied_config_events == feedback("commands/A")
  assert json.loads(Path(deployment_state.state_config_file_path("config_events.json")).read_text()) == feedback("commands/A")

  globals.config_events = feedback("commands/C")
  committed_document = copy.deepcopy(client.policies[NAME])
  mutations_before_plan = copy.deepcopy(client.mutations)
  for _ in range(3):
    # Reload state as a new CLI command does. Every save replaces the prior plan.
    deployment_state.initialize_last_applied_config_state()
    replacement = AllDeployer().plan()
    action = policy_action(replacement)
    assert action["action"] == "UPDATE"
    assert action["aws_policy_snapshot"]["document"] == committed_document
    assert not action["processed"]
    deployment_state.save_plan(replacement)
  assert client.mutations == mutations_before_plan

  later_group.fail = False
  AllDeployer().apply(deployment_state.load_plan())
  final = policy_action(deployment_state.load_plan())
  assert final["processed"]
  assert client.policies[NAME] == final["policy_document"]
  document = json.dumps(client.policies[NAME])
  assert "commands/C" in document
  assert "commands/A" not in document and "commands/B" not in document
  assert client.get_policy(policyName=NAME)["defaultVersionId"] == "3"
  assert client.attachments["certificate-a"] == {NAME}
  assert len([event for event in client.mutations if event[0] == "create_policy_version"]) == 2


@pytest.mark.parametrize("failure", ["journal-save", "response-lost"])
def test_replan_recovers_a_committed_update_without_its_processed_journal(
  pending_policy_update, monkeypatch, failure,
):
  client, later_group = pending_policy_update
  with monkeypatch.context() as interrupted:
    if failure == "journal-save":
      def fail_journal(*args):
        raise OSError("Journal save failed")

      interrupted.setattr(deployment_state, "mark_plan_action_processed", fail_journal)
      expected_error = OSError
    else:
      create_version = client.create_policy_version

      def lose_response(**kwargs):
        create_version(**kwargs)
        raise ConnectionError("Response lost")

      interrupted.setattr(client, "create_policy_version", lose_response)
      expected_error = ConnectionError
    with pytest.raises(expected_error):
      AllDeployer().apply(deployment_state.load_plan())
  saved = policy_action(deployment_state.load_plan())
  assert not saved["processed"]
  assert client.policies[NAME] == saved["policy_document"]
  assert deployment_state.last_applied_config_events == feedback("commands/A")

  globals.config_events = feedback("commands/C")
  replacement = AllDeployer().plan()
  assert policy_action(replacement)["action"] == "UPDATE"
  deployment_state.save_plan(replacement)
  later_group.fail = False
  AllDeployer().apply(deployment_state.load_plan())
  assert client.policies[NAME] == policy_action(deployment_state.load_plan())["policy_document"]
  assert client.get_policy(policyName=NAME)["defaultVersionId"] == "3"
  assert len([event for event in client.mutations if event[0] == "create_policy_version"]) == 2


def test_replan_keeps_ownership_after_an_intermediate_no_change_plan(pending_policy_update):
  client, _ = pending_policy_update
  apply_until_later_group_fails()
  unchanged = AllDeployer().plan()
  assert policy_action(unchanged)["action"] == "NO_CHANGE"
  deployment_state.save_plan(unchanged)
  globals.config_events = feedback("commands/C")
  client.mutations.clear()
  replacement = AllDeployer().plan()
  assert policy_action(replacement)["action"] == "UPDATE"
  assert policy_action(replacement)["aws_policy_snapshot"]["document"] == client.policies[NAME]
  assert client.mutations == []


@pytest.fixture
def pending_policy_create(pending_policy_update):
  client, later_group = pending_policy_update
  client.attachments.clear()
  client.delete_policy(policyName=NAME)
  plan = AllDeployer().plan()
  assert policy_action(plan)["action"] == "DEPLOY"
  deployment_state.save_plan(plan)
  client.mutations.clear()
  return client, later_group


def test_replan_recognizes_a_created_policy_without_a_prior_aws_snapshot(pending_policy_create):
  client, later_group = pending_policy_create
  apply_until_later_group_fails()
  assert policy_action(deployment_state.load_plan())["aws_policy_snapshot"] is None
  globals.config_events = feedback("commands/C")
  replacement = AllDeployer().plan()
  assert policy_action(replacement)["action"] == "UPDATE"
  deployment_state.save_plan(replacement)
  later_group.fail = False
  AllDeployer().apply(deployment_state.load_plan())
  assert "commands/C" in json.dumps(client.policies[NAME])
  assert len([event for event in client.mutations if event[0] == "create_policy"]) == 1


def test_replan_does_not_adopt_a_copied_document_in_another_account(
  pending_policy_create, monkeypatch,
):
  client, _ = pending_policy_create
  apply_until_later_group_fails()
  get_policy = client.get_policy

  def foreign_policy(**kwargs):
    result = get_policy(**kwargs)
    result["policyArn"] = f"arn:aws:iot:eu-west-1:999999999999:policy/{NAME}"
    return result

  monkeypatch.setattr(client, "get_policy", foreign_policy)
  globals.config_events = feedback("commands/C")
  client.mutations.clear()
  with pytest.raises(ValueError, match="manager-owned"):
    AllDeployer().plan()
  assert client.mutations == []


@pytest.mark.parametrize("invalid", [
  "policy_document", "aws_policy_snapshot", "delete_policy_version_id", "duplicate",
])
def test_replan_rejects_incomplete_or_ambiguous_ownership_records(pending_policy_update, invalid):
  client, _ = pending_policy_update
  apply_until_later_group_fails()
  saved = deployment_state.load_plan()
  action = policy_action(saved)
  if invalid == "duplicate":
    saved[0]["layers"][0]["actions"].append(copy.deepcopy(action))
  else:
    del action[invalid]
  deployment_state.save_plan(saved)
  globals.config_events = feedback("commands/C")
  client.mutations.clear()
  with pytest.raises(ValueError):
    AllDeployer().plan()
  assert client.mutations == []


@pytest.mark.parametrize("field,value", [
  ("group", "other_group"),
  ("layer", "other_layer"),
  ("resource", "OtherTwin-iot-policy"),
  ("resource_type", "iot_thing"),
  ("graph_id", "other_policy"),
  ("action", "DESTROY"),
])
def test_replan_rejects_ownership_records_for_another_resource(
  pending_policy_update, field, value,
):
  client, _ = pending_policy_update
  apply_until_later_group_fails()
  saved = deployment_state.load_plan()
  if field == "group":
    saved[0]["group"] = value
  elif field == "layer":
    saved[0]["layers"][0]["layer"] = value
  else:
    policy_action(saved)[field] = value
  deployment_state.save_plan(saved)
  globals.config_events = feedback("commands/C")
  client.mutations.clear()
  with pytest.raises(ValueError):
    AllDeployer().plan()
  assert client.mutations == []


@pytest.mark.parametrize("arn", [
  f"arn:aws:iot:eu-west-1:999999999999:policy/{NAME}",
  f"arn:aws:iot:us-east-1:123456789012:policy/{NAME}",
  f"arn:aws-cn:iot:eu-west-1:123456789012:policy/{NAME}",
  "arn:aws:iot:eu-west-1:123456789012:policy/OtherTwin-iot-policy",
])
def test_replan_rejects_ownership_records_for_another_aws_scope(
  pending_policy_update, arn,
):
  client, _ = pending_policy_update
  apply_until_later_group_fails()
  saved = deployment_state.load_plan()
  policy_action(saved)["aws_policy_snapshot"]["arn"] = arn
  deployment_state.save_plan(saved)
  globals.config_events = feedback("commands/C")
  client.mutations.clear()
  with pytest.raises(ValueError):
    AllDeployer().plan()
  assert client.mutations == []


@pytest.mark.parametrize("mismatch", ["saved-document", "live-document", "missing-plan"])
def test_replan_rejects_a_document_without_matching_ownership_evidence(
  pending_policy_update, mismatch,
):
  client, _ = pending_policy_update
  apply_until_later_group_fails()
  if mismatch == "saved-document":
    saved = deployment_state.load_plan()
    action = policy_action(saved)
    action["policy_document"] = json.loads(json.dumps(action["policy_document"]).replace("commands/B", "commands/unrelated"))
    deployment_state.save_plan(saved)
  elif mismatch == "live-document":
    document = json.dumps(client.policies[NAME]).replace("commands/B", "commands/unrelated")
    client.create_policy_version(policyName=NAME, policyDocument=document, setAsDefault=True)
  else:
    Path(deployment_state.state_plan_file_path()).unlink()
  globals.config_events = feedback("commands/C")
  client.mutations.clear()
  with pytest.raises(ValueError):
    AllDeployer().plan()
  assert client.mutations == []
