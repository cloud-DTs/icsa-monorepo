import copy
import json

import pytest

from tests.test_iot_policy_security import policy_environment
from tests.test_shared_iot_policy import POLICY_DOCUMENT

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.iot.all import AllDeployer as IotDeployer
from deployers.aws.iot.iot_policy import IotPolicyDeployer
from deployers.aws.iot.l1 import L1Deployer


NAME = "MGridICSA-iot-policy"


def install_legacy(client):
  client.create_policy(policyName=NAME, policyDocument=json.dumps(POLICY_DOCUMENT))
  client.mutations.clear()


def feedback(topic):
  return [{"action": {"feedback": {"type": "mqtt", "topic": topic}}}]


def test_plan_upgrades_the_known_permissive_policy_without_mutations(policy_environment):
  install_legacy(policy_environment)
  action = IotPolicyDeployer().plan()[-1]
  assert action["action"] == "UPDATE"
  assert action["aws_policy_snapshot"]["document"] == POLICY_DOCUMENT
  assert action["policy_document"] != POLICY_DOCUMENT
  assert policy_environment.mutations == []


def test_apply_upgrades_in_place_and_next_plan_is_no_change(policy_environment):
  install_legacy(policy_environment)
  arn = "certificate-a"
  policy_environment.attachments[arn] = {NAME}
  action = IotPolicyDeployer().plan()[-1]
  IotPolicyDeployer().apply(action, NAME)
  assert policy_environment.policies[NAME] == action["policy_document"]
  assert policy_environment.attachments[arn] == {NAME}
  assert policy_environment.get_policy(policyName=NAME)["defaultVersionId"] == "2"
  assert IotPolicyDeployer().plan()[-1]["action"] == "NO_CHANGE"
  assert [event[0] for event in policy_environment.mutations] == ["create_policy_version"]


def test_direct_deploy_also_upgrades_the_known_legacy_policy(policy_environment):
  install_legacy(policy_environment)
  IotPolicyDeployer().deploy()
  assert policy_environment.policies[NAME] != POLICY_DOCUMENT
  assert IotPolicyDeployer().plan()[-1]["action"] == "NO_CHANGE"


def test_configured_feedback_change_is_planned_as_an_update(policy_environment, monkeypatch):
  globals.config_events = feedback("commands/old")
  IotPolicyDeployer().deploy()
  monkeypatch.setattr(deployment_state, "last_applied_config_events", copy.deepcopy(globals.config_events))
  globals.config_events = feedback("commands/new")
  policy_environment.mutations.clear()
  action = IotPolicyDeployer().plan()[-1]
  assert action["action"] == "UPDATE"
  IotPolicyDeployer().apply(action, NAME)
  document = json.dumps(policy_environment.policies[NAME])
  assert "commands/new" in document and "commands/old" not in document


@pytest.mark.parametrize("field", ["policy_document", "aws_policy_snapshot", "delete_policy_version_id"])
def test_old_or_incomplete_saved_policy_plans_are_rejected(policy_environment, field):
  install_legacy(policy_environment)
  action = IotPolicyDeployer().plan()[-1]
  action.pop(field, None)
  with pytest.raises(ValueError, match="plan"):
    IotPolicyDeployer().apply(action, NAME)
  assert policy_environment.mutations == []


def test_changed_feedback_after_plan_is_rejected(policy_environment):
  install_legacy(policy_environment)
  action = IotPolicyDeployer().plan()[-1]
  globals.config_events = feedback("commands/new")
  with pytest.raises(ValueError, match="plan"):
    IotPolicyDeployer().apply(action, NAME)
  assert policy_environment.mutations == []


def test_aws_policy_drift_after_plan_is_rejected(policy_environment):
  install_legacy(policy_environment)
  action = IotPolicyDeployer().plan()[-1]
  policy_environment.policies[NAME]["Statement"][0]["Action"] = ["iot:Publish"]
  with pytest.raises(ValueError, match="plan"):
    IotPolicyDeployer().apply(action, NAME)
  assert policy_environment.mutations == []


def test_default_version_drift_with_identical_document_is_rejected(policy_environment):
  install_legacy(policy_environment)
  action = IotPolicyDeployer().plan()[-1]
  policy_environment.create_policy_version(policyName=NAME, policyDocument=json.dumps(POLICY_DOCUMENT), setAsDefault=True)
  policy_environment.mutations.clear()
  with pytest.raises(ValueError, match="plan"):
    IotPolicyDeployer().apply(action, NAME)
  assert policy_environment.mutations == []


def test_no_change_policy_is_checked_before_any_group_mutates(policy_environment, monkeypatch):
  IotPolicyDeployer().deploy()
  action = IotPolicyDeployer().plan()[-1]
  assert action["action"] == "NO_CHANGE"
  policy_environment.policies[NAME] = copy.deepcopy(POLICY_DOCUMENT)
  mutations = []

  class Probe:
    def apply(self, group_plan, phase):
      mutations.append(phase)

  monkeypatch.setattr(globals, "config_hierarchy", {}, raising=False)
  monkeypatch.setattr(IotDeployer, "LAYERS", [("iot_l1", L1Deployer)])
  monkeypatch.setattr(AllDeployer, "GROUP_DEPLOYERS", {"probe": Probe, "iot": IotDeployer})
  plan = [
    {"group": "probe", "layers": []},
    {"group": "iot", "layers": [{"layer": "iot_l1", "actions": [action]}]},
  ]
  with pytest.raises(ValueError, match="plan"):
    AllDeployer().apply(plan)
  assert mutations == []


def test_processed_policy_retry_accepts_desired_policy_but_rejects_drift(policy_environment):
  install_legacy(policy_environment)
  action = IotPolicyDeployer().plan()[-1]
  IotPolicyDeployer().apply(action, NAME)
  action["processed"] = True
  IotPolicyDeployer().validate_plan(action)
  policy_environment.policies[NAME] = copy.deepcopy(POLICY_DOCUMENT)
  with pytest.raises(ValueError, match="plan"):
    IotPolicyDeployer().validate_plan(action)


def test_full_version_capacity_deletes_only_the_planned_nondefault_version(policy_environment):
  install_legacy(policy_environment)
  for _ in range(4):
    policy_environment.create_policy_version(policyName=NAME, policyDocument=json.dumps(POLICY_DOCUMENT))
  policy_environment.mutations.clear()
  action = IotPolicyDeployer().plan()[-1]
  assert action["delete_policy_version_id"] == "2"
  assert policy_environment.mutations == []
  IotPolicyDeployer().apply(action, NAME)
  assert ("delete_policy_version", NAME, "2") in policy_environment.mutations
  assert all(event != ("delete_policy_version", NAME, "1") for event in policy_environment.mutations)
  assert len(policy_environment.policy_versions[NAME]) == 5
  assert policy_environment.get_policy(policyName=NAME)["defaultVersionId"] == "6"


def test_version_create_failure_keeps_the_active_legacy_default(policy_environment):
  install_legacy(policy_environment)
  action = IotPolicyDeployer().plan()[-1]
  policy_environment.errors["create_policy_version"] = "AccessDeniedException"
  with pytest.raises(ClientError):
    IotPolicyDeployer().apply(action, NAME)
  assert policy_environment.policies[NAME] == POLICY_DOCUMENT
  assert policy_environment.get_policy(policyName=NAME)["defaultVersionId"] == "1"


def test_unrelated_existing_document_is_not_adopted(policy_environment):
  document = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["iot:Publish"], "Resource": "*"}]}
  policy_environment.create_policy(policyName=NAME, policyDocument=json.dumps(document))
  policy_environment.mutations.clear()
  with pytest.raises(ValueError, match="match|owned"):
    IotPolicyDeployer().plan()
  assert policy_environment.mutations == []


def test_retry_after_version_slot_cleanup_preserves_default_and_finishes_update(policy_environment):
  install_legacy(policy_environment)
  for _ in range(4):
    policy_environment.create_policy_version(policyName=NAME, policyDocument=json.dumps(POLICY_DOCUMENT))
  action = IotPolicyDeployer().plan()[-1]
  policy_environment.errors["create_policy_version"] = "AccessDeniedException"
  with pytest.raises(ClientError):
    IotPolicyDeployer().apply(action, NAME)
  assert policy_environment.get_policy(policyName=NAME)["defaultVersionId"] == "1"
  assert len(policy_environment.policy_versions[NAME]) == 4
  policy_environment.errors.clear()
  IotPolicyDeployer().apply(action, NAME)
  assert policy_environment.policies[NAME] == action["policy_document"]
  assert ("delete_policy_version", NAME, "1") not in policy_environment.mutations


def test_missing_policy_action_cannot_hide_pending_thing_deploy(policy_environment):
  plan = {"layer": "iot_l1", "actions": [{"resource_type": "iot_thing", "resource": "MGridICSA-sensor-a", "action": "DEPLOY"}]}
  with pytest.raises(ValueError, match="plan"):
    L1Deployer().apply(plan, "DEPLOY")
  assert policy_environment.mutations == []


def test_policy_is_not_silently_recreated_or_upgraded_by_a_planned_thing(policy_environment, monkeypatch):
  from deployers.aws.iot.iot_thing import IotThingDeployer
  IotPolicyDeployer().deploy()
  action = IotPolicyDeployer().plan()[-1]
  assert action["action"] == "NO_CHANGE"
  policy_environment.policies[NAME] = copy.deepcopy(POLICY_DOCUMENT)
  policy_environment.mutations.clear()
  with pytest.raises(ValueError, match="plan"):
    IotThingDeployer().deploy({"id": "sensor-a"}, policy_action=action)
  assert policy_environment.mutations == []


def test_root_deploy_checks_policy_configuration_before_any_group_mutation(policy_environment, monkeypatch):
  globals.config_events = feedback("commands/*")
  monkeypatch.setattr(globals, "config_hierarchy", {}, raising=False)
  mutations = []

  class Probe:
    def deploy(self):
      mutations.append("deploy")

  monkeypatch.setattr(AllDeployer, "GROUP_DEPLOYERS", {"probe": Probe, "iot": IotDeployer})
  with pytest.raises(ValueError, match="topic"):
    AllDeployer().deploy()
  assert mutations == [] and policy_environment.mutations == []


@pytest.mark.parametrize("existing", [False, True], ids=["deploy", "update"])
@pytest.mark.parametrize("failure", ["state-save", "response-lost"])
def test_saved_apply_recovers_a_committed_policy_write_before_its_processed_flag(
  policy_environment, monkeypatch, tmp_path, existing, failure,
):
  if existing:
    install_legacy(policy_environment)
  monkeypatch.setattr(globals, "config_hierarchy", {}, raising=False)
  monkeypatch.setattr(globals, "iot_data_path", str(tmp_path / "keys"))
  monkeypatch.setattr(deployment_state, "last_applied_config_iot_devices", [])
  monkeypatch.setattr(deployment_state, "last_applied_config_hierarchy", {})
  monkeypatch.setenv(deployment_state.STATE_DIR_ENV, str(tmp_path / "state"))
  layer = L1Deployer()
  plan = layer.plan()
  deployment_state.save_plan([{"group": "iot", "layers": [plan]}])
  method = "create_policy_version" if existing else "create_policy"

  def saved_layer():
    return deployment_state.load_plan()[0]["layers"][0]

  if failure == "state-save":
    original = deployment_state.mark_plan_action_processed
    monkeypatch.setattr(deployment_state, "mark_plan_action_processed", lambda *args: (_ for _ in ()).throw(OSError("State save failed")))
    expected_error = OSError
  else:
    original = getattr(policy_environment, method)

    def commit_then_lose_response(**kwargs):
      original(**kwargs)
      raise ConnectionError("Response lost after AWS committed the policy write")

    monkeypatch.setattr(policy_environment, method, commit_then_lose_response)
    expected_error = ConnectionError
  with pytest.raises(expected_error):
    layer.apply(saved_layer(), "DEPLOY")
  action = next(a for a in saved_layer()["actions"] if a["resource_type"] == "iot_policy")
  assert not action["processed"]
  assert policy_environment.policies[NAME] == action["policy_document"]
  writes_before_retry = [m for m in policy_environment.mutations if m[0] == method]
  if failure == "state-save":
    monkeypatch.setattr(deployment_state, "mark_plan_action_processed", original)
  else:
    monkeypatch.setattr(policy_environment, method, original)
  layer.apply(saved_layer(), "DEPLOY")
  assert all(a["processed"] for a in saved_layer()["actions"])
  assert [m for m in policy_environment.mutations if m[0] == method] == writes_before_retry
  assert len(policy_environment.certificates) == 1
