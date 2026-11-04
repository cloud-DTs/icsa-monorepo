from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from tests.test_event_feedback_policy_updates import FeedbackIamClient
from tests.test_managed_lambda_regressions import ManagedLambdaFixture

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.core.cold_archive_mover_iam_role import ColdArchiveMoverIamRoleDeployer
from deployers.aws.core.l3_cold import L3ColdDeployer


POLICY_NAME = "ColdArchiveMoverScopedAccess"


class ColdArchivePolicyUpdateTests(ManagedLambdaFixture):
  def setUp(self):
    super().setUp()
    self.iam = FeedbackIamClient()
    patcher = patch.object(globals, "aws_iam_client", self.iam)
    patcher.start()
    self.addCleanup(patcher.stop)
    self.deployer = ColdArchiveMoverIamRoleDeployer()
    self.role_name = globals.cold_archive_mover_iam_role_name()

  def deploy_legacy_role(self):
    self.iam.create_role(RoleName=self.role_name)
    self.iam.policies[(self.role_name, POLICY_NAME)] = {
      "Version": "2012-10-17",
      "Statement": [
        {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{globals.cold_s3_bucket_name()}"},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:DeleteObject"], "Resource": f"arn:aws:s3:::{globals.cold_s3_bucket_name()}/*"},
        {"Effect": "Allow", "Action": "s3:PutObject", "Resource": f"arn:aws:s3:::{globals.archive_s3_bucket_name()}/*"},
      ],
    }
    self.iam.mutations.clear()

  def assert_version_permissions(self):
    document = self.iam.policies[(self.role_name, POLICY_NAME)]
    resources_by_action = {}
    for statement in document["Statement"]:
      actions = statement["Action"]
      for action in [actions] if isinstance(actions, str) else actions:
        resources_by_action[action] = statement["Resource"]
    cold_arn = f"arn:aws:s3:::{globals.cold_s3_bucket_name()}"
    archive_arn = f"arn:aws:s3:::{globals.archive_s3_bucket_name()}"
    self.assertEqual(cold_arn, resources_by_action.get("s3:ListBucketVersions"))
    for name in ("s3:GetObjectVersion", "s3:DeleteObjectVersion"):
      self.assertEqual(f"{cold_arn}/*", resources_by_action.get(name))
    self.assertEqual([cold_arn, archive_arn], resources_by_action.get("s3:GetBucketVersioning"))
    self.assertEqual(f"{archive_arn}/*", resources_by_action.get("s3:PutObject"))

  def test_new_role_has_scoped_version_permissions(self):
    self.deployer.deploy()
    self.assert_version_permissions()

  def test_existing_role_policy_updates_without_replacement(self):
    self.deploy_legacy_role()
    identity = copy.deepcopy(self.iam.roles[self.role_name])
    self.iam.policies[(self.role_name, "UnrelatedPolicy")] = {"Statement": []}
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.assertEqual([], self.iam.mutations)

    self.deployer.apply(action, action["resource"])

    self.assert_version_permissions()
    self.assertEqual(identity, self.iam.roles[self.role_name])
    self.assertEqual({"Statement": []}, self.iam.policies[(self.role_name, "UnrelatedPolicy")])
    self.assertEqual([], self.iam.deleted_roles)
    self.single_action(self.deployer.plan(), "NO_CHANGE")

  def test_missing_inline_policy_is_repaired(self):
    self.deploy_legacy_role()
    del self.iam.policies[(self.role_name, POLICY_NAME)]
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.deployer.apply(action, action["resource"])
    self.assert_version_permissions()

  def test_missing_role_is_recreated(self):
    action = self.single_action(self.deployer.plan(), "DEPLOY")
    self.deployer.apply(action, action["resource"])
    self.assert_version_permissions()

  def test_encoded_aws_policy_is_accepted(self):
    self.deployer.deploy()
    self.iam.encoded_documents = True
    self.single_action(self.deployer.plan(), "NO_CHANGE")

  def test_aws_drift_is_rejected_before_any_group_is_applied(self):
    self.deploy_legacy_role()
    action = self.single_action(self.deployer.plan(), "UPDATE")
    self.iam.policies[(self.role_name, POLICY_NAME)]["Statement"] = []
    self.assert_rejected_before_any_group(self.plan_for_group("core", "core_l3_cold", [action]))
    self.assertEqual([], self.iam.mutations)

  def test_unchanged_policy_is_also_checked_before_apply(self):
    self.deployer.deploy()
    action = self.single_action(self.deployer.plan(), "NO_CHANGE")
    self.iam.policies[(self.role_name, POLICY_NAME)]["Statement"] = []
    self.assert_rejected_before_any_group(self.plan_for_group("core", "core_l3_cold", [action]))

  def test_changed_local_policy_is_rejected(self):
    self.deploy_legacy_role()
    action = self.single_action(self.deployer.plan(), "UPDATE")
    with patch.object(globals, "archive_s3_bucket_name", return_value="other-archive"):
      with self.assertRaises(ValueError):
        self.deployer.apply(action, action["resource"])
    self.assertEqual([], self.iam.mutations)

  def test_role_created_after_plan_is_rejected(self):
    action = self.single_action(self.deployer.plan(), "DEPLOY")
    self.iam.create_role(RoleName=self.role_name)
    self.iam.mutations.clear()
    self.assert_rejected_before_any_group(self.plan_for_group("core", "core_l3_cold", [action]))
    self.assertEqual([], self.iam.mutations)

  def test_policy_read_denied_does_not_plan_replacement(self):
    self.deploy_legacy_role()
    self.iam.read_errors["GetRolePolicy"] = ClientError(
      {"Error": {"Code": "AccessDenied"}}, "GetRolePolicy",
    )
    with self.assertRaises(ClientError):
      self.deployer.plan()
    self.assertEqual([], self.iam.mutations)

  def test_cold_layer_applies_iam_update(self):
    self.deploy_legacy_role()
    action = self.single_action(self.deployer.plan(), "UPDATE")
    with patch.object(deployment_state, "mark_plan_action_processed") as processed:
      L3ColdDeployer().apply({"layer": "core_l3_cold", "actions": [action]}, "DEPLOY")
    processed.assert_called_once_with("core", "core_l3_cold", action)
    self.assert_version_permissions()


if __name__ == "__main__":
  unittest.main()
