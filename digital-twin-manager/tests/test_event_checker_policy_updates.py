from __future__ import annotations

import copy
import json
import types
from unittest.mock import patch

from tests.test_managed_lambda_regressions import ManagedLambdaFixture
from tests.test_event_feedback_policy_updates import FeedbackIamClient

from botocore.exceptions import ClientError
import globals
from deployers.aws.core.event_checker_iam_role import EventCheckerIamRoleDeployer
from deployers.aws.core.event_checker_lambda_function import EventCheckerLambdaFunctionDeployer
from deployers.aws.core.l2 import L2Deployer


POLICY_NAME = "EventCheckerScopedAccess"
WORKSPACE = "arn:aws:iottwinmaker:eu-west-1:123456789012:workspace/dt-twinmaker"


def actions(statement):
  value = statement["Action"]
  return [value] if isinstance(value, str) else value


class EventCheckerPolicyUpdateTests(ManagedLambdaFixture):
  def setUp(self):
    super().setUp()
    self.iam = FeedbackIamClient()
    for name, value in (
      ("aws_iam_client", self.iam),
      ("aws_twinmaker_client", types.SimpleNamespace(meta=types.SimpleNamespace(region_name="eu-west-1"))),
      ("aws_sf_client", types.SimpleNamespace(meta=types.SimpleNamespace(region_name="eu-west-1"))),
    ):
      patcher = patch.object(globals, name, value)
      patcher.start()
      self.addCleanup(patcher.stop)
    self.deployer = EventCheckerIamRoleDeployer()
    self.role_name = globals.event_checker_iam_role_name()

  def deploy_current(self):
    self.deployer.deploy()
    self.iam.mutations.clear()
    return copy.deepcopy(self.iam.roles[self.role_name])

  def deploy_legacy(self):
    role = self.deploy_current()
    document = self.iam.policies[(self.role_name, POLICY_NAME)]
    statements = []
    for statement in document["Statement"]:
      remaining = [action for action in actions(statement) if action != "iottwinmaker:GetWorkspace"]
      if remaining:
        statement["Action"] = remaining
        statements.append(statement)
    document["Statement"] = statements
    return role

  def assert_root_rejects(self, planned):
    self.assert_rejected_before_any_group(self.plan_for_group("core", "core_l2", planned))
    self.assertEqual([], self.iam.mutations)

  def test_new_role_grants_workspace_read_only_for_its_workspace(self):
    self.deploy_current()
    document = self.iam.policies[(self.role_name, POLICY_NAME)]
    resources = {
      resource
      for statement in document["Statement"]
      if "iottwinmaker:GetWorkspace" in actions(statement)
      for resource in ([statement["Resource"]] if isinstance(statement["Resource"], str) else statement["Resource"])
    }
    self.assertEqual({WORKSPACE}, resources)
    permitted = {action for statement in document["Statement"] for action in actions(statement)}
    self.assertTrue({"iottwinmaker:GetPropertyValue", "iottwinmaker:GetPropertyValueHistory",
                     "lambda:GetFunction", "lambda:InvokeFunction", "states:StartExecution"} <= permitted)

  def test_new_role_grants_entity_and_component_reads_only_in_its_workspace(self):
    self.deploy_current()
    document = self.iam.policies[(self.role_name, POLICY_NAME)]
    for action, child_type in (
      ("iottwinmaker:GetComponentType", "component-type"),
      ("iottwinmaker:GetEntity", "entity"),
    ):
      with self.subTest(action=action):
        resources = {
          resource
          for statement in document["Statement"]
          if statement["Effect"] == "Allow" and action in actions(statement)
          for resource in ([statement["Resource"]] if isinstance(statement["Resource"], str) else statement["Resource"])
        }
        self.assertEqual({WORKSPACE, f"{WORKSPACE}/{child_type}/*"}, resources)

  def test_policy_with_workspace_access_adds_missing_metadata_reads_in_place(self):
    original = self.deploy_current()
    attachments = copy.deepcopy(self.iam.attachments)
    for missing_permissions in (
      {"iottwinmaker:GetComponentType", "iottwinmaker:GetEntity"},
      {"iottwinmaker:GetComponentType"},
      {"iottwinmaker:GetEntity"},
    ):
      with self.subTest(missing_permissions=sorted(missing_permissions)):
        document = self.iam.policies[(self.role_name, POLICY_NAME)]
        document["Statement"] = [
          statement for statement in document["Statement"]
          if not missing_permissions.intersection(actions(statement))
        ]
        self.iam.mutations.clear()
        planned = self.single_action(self.deployer.plan(), "UPDATE")
        self.assertEqual([], self.iam.mutations)

        saved = json.loads(json.dumps(planned))
        self.deployer.apply(saved, saved["resource"])

        updated = self.iam.policies[(self.role_name, POLICY_NAME)]
        permitted = {action for statement in updated["Statement"] for action in actions(statement)}
        self.assertTrue({"iottwinmaker:GetWorkspace", "iottwinmaker:GetComponentType",
                         "iottwinmaker:GetEntity"} <= permitted)
        self.assertEqual(original, self.iam.roles[self.role_name])
        self.assertEqual(attachments, self.iam.attachments)
        self.assertEqual([("put_role_policy", self.role_name, POLICY_NAME)], self.iam.mutations)
        self.assertEqual([], self.iam.deleted_roles)
        self.single_action(self.deployer.plan(), "NO_CHANGE")

  def test_legacy_policy_updates_in_place_and_next_plan_has_no_change(self):
    original = self.deploy_legacy()
    attachments = copy.deepcopy(self.iam.attachments)
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.assertEqual([], self.iam.mutations)
    saved = json.loads(json.dumps(action))  # Exercise saved-plan metadata.

    self.deployer.apply(saved, saved["resource"])

    self.assertEqual(original, self.iam.roles[self.role_name])
    self.assertEqual(attachments, self.iam.attachments)
    self.assertEqual([("put_role_policy", self.role_name, POLICY_NAME)], self.iam.mutations)
    self.assertEqual([], self.iam.deleted_roles)
    self.assertEqual("NO_CHANGE", self.deployer.plan()[0]["action"])

  def test_missing_policy_is_added_without_replacing_existing_role(self):
    original = self.deploy_current()
    del self.iam.policies[(self.role_name, POLICY_NAME)]
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.deployer.apply(action, action["resource"])
    self.assertEqual(original, self.iam.roles[self.role_name])
    self.assertEqual("NO_CHANGE", self.deployer.plan()[0]["action"])

  def test_missing_role_plans_deploy_and_creates_correct_policy(self):
    action = self.single_action(self.deployer.plan(), "DEPLOY")
    self.assertEqual([], self.iam.mutations)
    self.deployer.apply(action, action["resource"])
    self.assertEqual([self.role_name], self.iam.created_roles)
    self.assertEqual("NO_CHANGE", self.deployer.plan()[0]["action"])

  def test_matching_url_encoded_policy_needs_no_update(self):
    self.deploy_current()
    self.iam.encoded_documents = True
    self.single_action(self.deployer.plan(), "NO_CHANGE")
    self.assertEqual([], self.iam.mutations)

  def test_url_encoded_legacy_policy_can_be_updated(self):
    self.deploy_legacy()
    self.iam.encoded_documents = True
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.deployer.apply(action, action["resource"])
    self.single_action(self.deployer.plan(), "NO_CHANGE")

  def test_aws_policy_drift_is_detected_when_local_config_does_not_change(self):
    self.deploy_current()
    self.iam.policies[(self.role_name, POLICY_NAME)]["Statement"] = []
    self.single_action(self.deployer.plan(), "UPDATE")
    self.assertEqual([], self.iam.mutations)

  def test_access_denied_is_not_interpreted_as_missing_role_or_policy(self):
    self.deploy_current()
    for operation in ("GetRole", "GetRolePolicy"):
      with self.subTest(operation=operation):
        self.iam.read_errors[operation] = ClientError({"Error": {"Code": "AccessDenied"}}, operation)
        try:
          with self.assertRaises(ClientError):
            self.deployer.plan()
        finally:
          self.iam.read_errors.clear()
    self.assertEqual([], self.iam.mutations)

  def test_apply_rejects_unplanned_target_role(self):
    self.deploy_legacy()
    action = self.single_action(self.deployer.plan(), "UPDATE")
    with self.assertRaises(ValueError):
      self.deployer.apply(action, "another-role")
    self.assertEqual([], self.iam.mutations)

  def test_current_configuration_change_invalidates_saved_update(self):
    self.deploy_legacy()
    action = self.single_action(self.deployer.plan(), "UPDATE")
    with patch.object(globals, "twinmaker_workspace_name", return_value="other-workspace"):
      with self.assertRaises(ValueError):
        self.deployer.apply(action, action["resource"])
    self.assertEqual([], self.iam.mutations)

  def test_policy_change_after_update_plan_is_rejected_before_any_mutation(self):
    self.deploy_legacy()
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.iam.policies[(self.role_name, POLICY_NAME)]["Statement"] = []
    with self.assertRaises(ValueError):
      self.deployer.apply(action, action["resource"])
    self.assert_root_rejects([action])

  def test_policy_change_after_no_change_plan_is_rejected_before_any_group(self):
    self.deploy_current()
    planned = self.deployer.plan()
    self.single_action(planned, "NO_CHANGE")
    self.iam.policies[(self.role_name, POLICY_NAME)]["Statement"] = []
    self.assert_root_rejects(planned)

  def test_local_change_after_no_change_plan_is_rejected_before_any_group(self):
    self.deploy_current()
    planned = self.deployer.plan()
    with patch.object(globals, "twinmaker_workspace_name", return_value="other-workspace"):
      self.assert_root_rejects(planned)

  def test_missing_saved_policy_metadata_requires_replanning(self):
    self.deploy_current()
    planned = self.deployer.plan()
    for key in ("policy_document", "aws_policy_document"):
      with self.subTest(key=key):
        legacy = copy.deepcopy(planned)
        legacy[0].pop(key, None)
        self.assert_root_rejects(legacy)

  def test_deleted_role_invalidates_saved_update(self):
    self.deploy_legacy()
    planned = self.deployer.plan()
    self.iam.roles.pop(self.role_name)
    self.assert_root_rejects(planned)

  def test_role_created_after_deploy_plan_is_rejected_before_any_group(self):
    planned = self.deployer.plan()
    self.single_action(planned, "DEPLOY")
    self.iam.create_role(RoleName=self.role_name)
    self.iam.mutations.clear()
    self.assert_root_rejects(planned)

  def test_iam_update_is_processed_before_dependent_checker_lambda(self):
    original = self.deploy_legacy()
    self.iam.create_role(RoleName=globals.event_feedback_iam_role_name())
    checker, name = self.deploy_core(EventCheckerLambdaFunctionDeployer)
    self.change_source(self.sources["event-checker"])
    role_action = self.single_action(self.deployer.plan(), "UPDATE")
    checker_action = self.single_action(checker.plan(), "UPDATE")
    journal = []
    original_update = self.lambda_client.update_function_code

    def update_with_ready_policy(**request):
      self.assertEqual("NO_CHANGE", self.deployer.plan()[0]["action"])
      self.assertEqual([("UPDATE", "iam")], journal)
      return original_update(**request)

    def record_processed(group, layer, action):
      journal.append((action["action"], action["resource_type"]))

    self.iam.mutations.clear()
    with patch.object(self.lambda_client, "update_function_code", side_effect=update_with_ready_policy):
      with patch("deployment_state.mark_plan_action_processed", side_effect=record_processed):
        L2Deployer().apply({"layer": "core_l2", "actions": [checker_action, role_action]}, "DEPLOY")
    self.assertEqual(original, self.iam.roles[self.role_name])
    self.assertEqual([("UPDATE", "iam"), ("UPDATE", "lambda_function")], journal)
    self.assertEqual([], self.iam.deleted_roles)
    self.assertEqual([], self.lambda_client.delete_requests)
