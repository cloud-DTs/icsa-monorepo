from __future__ import annotations

import copy
import io
import json
import types
import unittest
import zipfile
from urllib.parse import quote
from unittest.mock import patch

from tests.test_managed_lambda_regressions import ManagedLambdaFixture

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.core.event_checker_lambda_function import EventCheckerLambdaFunctionDeployer
from deployers.aws.core.event_feedback_iam_role import EventFeedbackIamRoleDeployer
from deployers.aws.core.l2 import L2Deployer


POLICY_NAME = "EventFeedbackScopedAccess"
ACCOUNT_ID = "123456789012"
REGION = "eu-west-1"


def feedback_events(*topics):
  return [
    {
      "condition": f"root.sensor.temperature > DOUBLE({index + 10})",
      "action": {
        "type": "lambda",
        "functionName": f"callback-{index}",
        "external": True,
        "feedback": {"type": "mqtt", "topic": topic, "payload": "action-result"},
      },
    }
    for index, topic in enumerate(topics)
  ]


def topic_arn(topic):
  return f"arn:aws:iot:{REGION}:{ACCOUNT_ID}:topic/{topic}"


class FeedbackIamClient:
  """IAM boundary that keeps role identity, inline policies and permissions."""

  def __init__(self):
    self.meta = types.SimpleNamespace(region_name=REGION)
    self.roles = {}
    self.policies = {}
    self.attachments = {}
    self.created_roles = []
    self.deleted_roles = []
    self.mutations = []
    self.read_errors = {}
    self.encoded_documents = False
    self.role_counter = 0

  def _missing(self, operation):
    raise ClientError({"Error": {"Code": "NoSuchEntity"}}, operation)

  def _read_error(self, operation):
    if operation in self.read_errors:
      raise self.read_errors[operation]

  def create_role(self, RoleName, **request):
    if RoleName in self.roles:
      raise ClientError({"Error": {"Code": "EntityAlreadyExists"}}, "CreateRole")
    self.role_counter += 1
    self.roles[RoleName] = {
      "RoleName": RoleName,
      "Arn": f"arn:aws:iam::{ACCOUNT_ID}:role/{RoleName}",
      "RoleId": f"role-identity-{self.role_counter}",
      "AssumeRolePolicyDocument": json.loads(request.get("AssumeRolePolicyDocument", "{}")),
    }
    self.attachments[RoleName] = set()
    self.created_roles.append(RoleName)
    self.mutations.append(("create_role", RoleName))
    return {"Role": copy.deepcopy(self.roles[RoleName])}

  def get_role(self, RoleName):
    self._read_error("GetRole")
    if RoleName not in self.roles:
      self._missing("GetRole")
    return {"Role": copy.deepcopy(self.roles[RoleName])}

  def get_role_policy(self, RoleName, PolicyName):
    self._read_error("GetRolePolicy")
    key = (RoleName, PolicyName)
    if RoleName not in self.roles or key not in self.policies:
      self._missing("GetRolePolicy")
    document = copy.deepcopy(self.policies[key])
    if self.encoded_documents:
      document = quote(json.dumps(document), safe="")
    return {"RoleName": RoleName, "PolicyName": PolicyName, "PolicyDocument": document}

  def put_role_policy(self, RoleName, PolicyName, PolicyDocument):
    if RoleName not in self.roles:
      self._missing("PutRolePolicy")
    document = json.loads(PolicyDocument) if isinstance(PolicyDocument, str) else copy.deepcopy(PolicyDocument)
    self.policies[(RoleName, PolicyName)] = document
    self.mutations.append(("put_role_policy", RoleName, PolicyName))
    return {}

  def delete_role_policy(self, RoleName, PolicyName):
    key = (RoleName, PolicyName)
    if key not in self.policies:
      self._missing("DeleteRolePolicy")
    del self.policies[key]
    self.mutations.append(("delete_role_policy", RoleName, PolicyName))
    return {}

  def attach_role_policy(self, RoleName, PolicyArn):
    if RoleName not in self.roles:
      self._missing("AttachRolePolicy")
    self.attachments[RoleName].add(PolicyArn)
    self.mutations.append(("attach_role_policy", RoleName, PolicyArn))

  def list_attached_role_policies(self, RoleName):
    if RoleName not in self.roles:
      self._missing("ListAttachedRolePolicies")
    return {"AttachedPolicies": [{"PolicyArn": arn} for arn in sorted(self.attachments[RoleName])]}

  def detach_role_policy(self, RoleName, PolicyArn):
    self.attachments[RoleName].discard(PolicyArn)
    self.mutations.append(("detach_role_policy", RoleName, PolicyArn))

  def list_role_policies(self, RoleName):
    if RoleName not in self.roles:
      self._missing("ListRolePolicies")
    return {"PolicyNames": [name for role, name in self.policies if role == RoleName]}

  def list_instance_profiles_for_role(self, RoleName):
    return {"InstanceProfiles": []}

  def delete_role(self, RoleName):
    if RoleName not in self.roles:
      self._missing("DeleteRole")
    del self.roles[RoleName]
    self.deleted_roles.append(RoleName)
    self.mutations.append(("delete_role", RoleName))

  def publish_resources(self, role_name):
    resources = set()
    for (role, _), document in self.policies.items():
      if role != role_name:
        continue
      statements = document.get("Statement", [])
      if isinstance(statements, dict):
        statements = [statements]
      for statement in statements:
        actions = statement.get("Action", [])
        actions = [actions] if isinstance(actions, str) else actions
        if statement.get("Effect") == "Allow" and "iot:Publish" in actions:
          permitted = statement.get("Resource", [])
          resources.update([permitted] if isinstance(permitted, str) else permitted)
    return resources


class EventFeedbackPolicyUpdateTests(ManagedLambdaFixture):
  def setUp(self):
    super().setUp()
    self.iam = FeedbackIamClient()
    patcher = patch.object(globals, "aws_iam_client", self.iam)
    patcher.start()
    self.addCleanup(patcher.stop)
    patcher = patch.object(globals, "aws_iot_client", types.SimpleNamespace(meta=types.SimpleNamespace(region_name=REGION)))
    patcher.start()
    self.addCleanup(patcher.stop)
    self.deployer = EventFeedbackIamRoleDeployer()
    self.role_name = globals.event_feedback_iam_role_name()

  def deploy_feedback(self, *topics):
    globals.config_events = feedback_events(*topics)
    deployment_state.last_applied_config_events = copy.deepcopy(globals.config_events)
    self.deployer.deploy()
    self.iam.mutations.clear()
    return copy.deepcopy(self.iam.roles[self.role_name])

  def assert_topics(self, *topics):
    self.assertEqual({topic_arn(topic) for topic in topics}, self.iam.publish_resources(self.role_name))

  def apply_update(self, *topics):
    original_role = copy.deepcopy(self.iam.roles[self.role_name])
    original_create_count = len(self.iam.created_roles)
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.assertEqual([], self.iam.mutations, "Planning must not change IAM.")

    self.deployer.apply(action, action["resource"])

    self.assert_topics(*topics)
    self.assertEqual(original_role, self.iam.roles[self.role_name])
    self.assertEqual(original_create_count, len(self.iam.created_roles))
    self.assertEqual([], self.iam.deleted_roles)
    self.assertEqual("NO_CHANGE", self.deployer.plan()[0]["action"])
    return action

  def assert_policy_rejected_before_groups(self, actions):
    plan = self.plan_for_group("core", "core_l2", actions)
    self.assert_rejected_before_any_group(plan)
    self.assertEqual([], self.iam.mutations)

  def test_topic_rename_updates_publish_permissions_without_replacing_role(self):
    self.deploy_feedback("topic-old")
    globals.config_events = feedback_events("topic-new")

    self.apply_update("topic-new")

  def test_first_mqtt_feedback_adds_policy_to_existing_role(self):
    self.deploy_feedback()
    self.assertNotIn((self.role_name, POLICY_NAME), self.iam.policies)
    globals.config_events = feedback_events("topic-new")

    self.apply_update("topic-new")

  def test_remove_last_mqtt_feedback_deletes_policy_and_preserves_role(self):
    self.deploy_feedback("topic-old")
    globals.config_events = []

    action = self.apply_update()

    self.assertIn("policy_document", action)
    self.assertIsNone(action["policy_document"])
    self.assertNotIn((self.role_name, POLICY_NAME), self.iam.policies)

  def test_narrowing_topics_removes_old_publish_permissions(self):
    self.deploy_feedback("topic-keep", "topic-remove")
    globals.config_events = feedback_events("topic-keep")

    self.apply_update("topic-keep")

  def test_matching_topics_ignore_event_order_and_duplicates(self):
    self.deploy_feedback("topic-b", "topic-a")
    globals.config_events = feedback_events("topic-a", "topic-b", "topic-a")

    self.single_action(self.deployer.plan(), "NO_CHANGE")

    self.assert_topics("topic-a", "topic-b")
    self.assertEqual([], self.iam.mutations)

  def test_iot_device_id_feedback_uses_twin_prefixed_topic_on_update(self):
    self.deploy_feedback("topic-old")
    globals.config_events = feedback_events("unused")
    feedback = globals.config_events[0]["action"]["feedback"]
    del feedback["topic"]
    feedback["iotDeviceId"] = "sensor-a"

    self.apply_update("dt-sensor-a")

  def test_missing_inline_policy_is_added_to_existing_role(self):
    self.deploy_feedback("topic-current")
    del self.iam.policies[(self.role_name, POLICY_NAME)]

    self.apply_update("topic-current")

  def test_absent_role_plans_deployment_and_apply_creates_policy(self):
    globals.config_events = feedback_events("topic-current")

    action = self.single_action(self.deployer.plan(), "DEPLOY")
    self.deployer.apply(action, action["resource"])

    self.assert_topics("topic-current")
    self.assertEqual([self.role_name], self.iam.created_roles)
    self.assertEqual([], self.iam.deleted_roles)

  def test_deploy_rejects_target_role_different_from_saved_plan(self):
    globals.config_events = feedback_events("topic-current")
    action = self.single_action(self.deployer.plan(), "DEPLOY")

    with self.assertRaises(ValueError):
      self.deployer.apply(action, "unplanned-role")

    self.assertEqual({}, self.iam.roles)
    self.assertEqual({}, self.iam.policies)
    self.assertEqual([], self.iam.mutations)

  def test_role_created_after_deploy_plan_rejects_root_apply_before_groups(self):
    globals.config_events = feedback_events("topic-current")
    actions = self.deployer.plan()
    self.single_action(actions, "DEPLOY")
    self.iam.create_role(RoleName=self.role_name)
    other_role = copy.deepcopy(self.iam.roles[self.role_name])
    self.iam.mutations.clear()

    self.assert_policy_rejected_before_groups(actions)

    self.assertEqual(other_role, self.iam.roles[self.role_name])
    self.assertEqual({}, self.iam.policies)
    self.assertEqual([], self.iam.deleted_roles)

  def test_access_denied_on_deploy_absence_check_stops_root_before_groups(self):
    globals.config_events = feedback_events("topic-current")
    actions = self.deployer.plan()
    self.single_action(actions, "DEPLOY")
    self.iam.read_errors["GetRole"] = ClientError({"Error": {"Code": "AccessDenied"}}, "GetRole")
    plan = self.plan_for_group("core", "core_l2", actions)

    with patch.object(AllDeployer, "_apply_group") as apply_group:
      with self.assertRaises(ClientError):
        AllDeployer().apply(plan)
      apply_group.assert_not_called()

    self.assertEqual({}, self.iam.roles)
    self.assertEqual([], self.iam.mutations)

  def test_access_denied_reading_policy_is_not_treated_as_missing_policy(self):
    self.deploy_feedback("topic-current")
    self.iam.read_errors["GetRolePolicy"] = ClientError({"Error": {"Code": "AccessDenied"}}, "GetRolePolicy")

    with self.assertRaises(ClientError):
      self.deployer.plan()

    self.assertEqual([], self.iam.mutations)

  def test_access_denied_distinguishing_role_from_missing_policy_propagates(self):
    self.deploy_feedback("topic-current")
    del self.iam.policies[(self.role_name, POLICY_NAME)]
    self.iam.read_errors["GetRole"] = ClientError({"Error": {"Code": "AccessDenied"}}, "GetRole")

    with self.assertRaises(ClientError):
      self.deployer.plan()

    self.assertEqual([], self.iam.mutations)

  def test_encoded_matching_policy_has_no_change(self):
    self.deploy_feedback("topic-current")
    self.iam.encoded_documents = True

    self.single_action(self.deployer.plan(), "NO_CHANGE")

    self.assertEqual([], self.iam.mutations)

  def test_encoded_stale_policy_can_be_updated(self):
    self.deploy_feedback("topic-old")
    self.iam.encoded_documents = True
    globals.config_events = feedback_events("topic-new")

    self.apply_update("topic-new")

  def test_policy_drift_in_aws_updates_even_when_local_configs_match(self):
    self.deploy_feedback("topic-current")
    document = self.iam.policies[(self.role_name, POLICY_NAME)]
    document["Statement"][0]["Resource"] = [topic_arn("topic-stale")]

    self.apply_update("topic-current")

  def test_policy_config_change_after_update_plan_rejects_before_mutation(self):
    self.deploy_feedback("topic-old")
    globals.config_events = feedback_events("topic-new")
    action = self.single_action(self.deployer.plan(), "UPDATE")
    globals.config_events = feedback_events("topic-after-plan")

    with self.assertRaises(ValueError):
      self.deployer.apply(action, action["resource"])

    self.assert_topics("topic-old")
    self.assertEqual([], self.iam.mutations)

  def test_removal_plan_cannot_delete_policy_if_feedback_was_added_after_plan(self):
    self.deploy_feedback("topic-old")
    globals.config_events = []
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.assertIn("policy_document", action)
    self.assertIsNone(action["policy_document"])
    globals.config_events = feedback_events("topic-after-plan")

    with self.assertRaises(ValueError):
      self.deployer.apply(action, action["resource"])

    self.assert_topics("topic-old")
    self.assertEqual([], self.iam.mutations)

  def test_saved_update_plan_without_desired_policy_metadata_is_rejected(self):
    self.deploy_feedback("topic-old")
    globals.config_events = []
    action = self.single_action(self.deployer.plan(), "UPDATE")
    action.pop("policy_document", None)

    with self.assertRaises(ValueError):
      self.deployer.apply(action, action["resource"])

    self.assert_topics("topic-old")
    self.assertEqual([], self.iam.mutations)

  def test_policy_aws_drift_after_update_plan_is_rejected_before_mutation(self):
    self.deploy_feedback("topic-old")
    globals.config_events = feedback_events("topic-new")
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.iam.policies[(self.role_name, POLICY_NAME)]["Statement"][0]["Resource"] = [topic_arn("topic-other-writer")]

    with self.assertRaises(ValueError):
      self.deployer.apply(action, action["resource"])

    self.assert_topics("topic-other-writer")
    self.assertEqual([], self.iam.mutations)

  def test_local_topics_changed_after_no_change_plan_reject_root_apply(self):
    self.deploy_feedback("topic-old")
    actions = self.deployer.plan()
    self.single_action(actions, "NO_CHANGE")
    globals.config_events = feedback_events("topic-after-plan")

    self.assert_policy_rejected_before_groups(actions)

  def test_aws_policy_changed_after_no_change_plan_rejects_root_apply(self):
    self.deploy_feedback("topic-old")
    actions = self.deployer.plan()
    self.single_action(actions, "NO_CHANGE")
    self.iam.policies[(self.role_name, POLICY_NAME)]["Statement"][0]["Resource"] = [topic_arn("topic-other-writer")]

    self.assert_policy_rejected_before_groups(actions)

  def test_saved_no_change_plan_without_policy_metadata_rejects_root_apply(self):
    self.deploy_feedback()
    actions = self.deployer.plan()
    self.single_action(actions, "NO_CHANGE")
    actions[0].pop("policy_document", None)

    self.assert_policy_rejected_before_groups(actions)

  def test_core_l2_updates_feedback_policy_before_checker_code_and_journal(self):
    original_role = self.deploy_feedback("topic-old")
    self.iam.create_role(RoleName=globals.event_checker_iam_role_name())
    checker, checker_name = self.deploy_core(EventCheckerLambdaFunctionDeployer)
    original_checker_arn = self.lambda_client.functions[checker_name]["FunctionArn"]
    globals.config_events = feedback_events("topic-new")
    role_action = self.single_action(self.deployer.plan(), "UPDATE")
    checker_action = self.single_action(checker.plan(), "UPDATE")
    layer_plan = {"layer": "core_l2", "actions": [checker_action, role_action]}
    journal = []
    original_code_update = self.lambda_client.update_function_code

    def update_code_with_ready_permissions(**request):
      self.assert_topics("topic-new")
      self.assertEqual(original_role, self.iam.roles[self.role_name])
      self.assertEqual([("UPDATE", "iam")], journal)
      return original_code_update(**request)

    def record_processed(group, layer, action):
      self.assertEqual("core", group)
      self.assertEqual("core_l2", layer)
      self.assert_topics("topic-new")
      if action["resource_type"] == "lambda_function":
        with zipfile.ZipFile(io.BytesIO(self.lambda_client.packages[checker_name])) as package:
          self.assertEqual(globals.config_events, json.loads(package.read("config_events.json")))
        self.assertEqual("Successful", self.lambda_client.functions[checker_name]["LastUpdateStatus"])
      journal.append((action["action"], action["resource_type"]))

    self.iam.mutations.clear()
    with patch.object(self.lambda_client, "update_function_code", side_effect=update_code_with_ready_permissions):
      with patch("deployment_state.mark_plan_action_processed", side_effect=record_processed):
        L2Deployer().apply(layer_plan, "DEPLOY")

    self.assertEqual([("UPDATE", "iam"), ("UPDATE", "lambda_function")], journal)
    self.assertEqual(original_checker_arn, self.lambda_client.functions[checker_name]["FunctionArn"])
    self.assertEqual(original_role, self.iam.roles[self.role_name])
    self.assertEqual([], self.iam.deleted_roles)
    self.assertEqual([], self.lambda_client.delete_requests)


if __name__ == "__main__":
  unittest.main()
