from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tests.aws_stubs import StubAwsClient, StubStsClient, install_aws_stubs

install_aws_stubs()

import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.core.all import AllDeployer as CoreAllDeployer
from deployers.aws.core.hot_reader_iam_role import HotReaderIamRoleDeployer
from deployers.aws.core.hot_reader_lambda_function import HotReaderLambdaFunctionDeployer
from deployers.aws.core.l3_hot import L3HotDeployer
from tests.test_hot_reader_policy_updates import PolicyIamClient
from tests.test_hot_reader_updates import UpdatingLambdaClient, package_hash


class HotReaderApplyTests(unittest.TestCase):
  def setUp(self):
    temporary_directory = tempfile.TemporaryDirectory()
    self.addCleanup(temporary_directory.cleanup)
    self.folder = Path(temporary_directory.name)
    self.source = self.folder / "core" / "hot-reader" / "lambda_function.py"
    self.source.parent.mkdir(parents=True)
    self.source.write_bytes(b"def lambda_handler(event, context):\n  return event\n")
    self.iam = PolicyIamClient()
    self.lambda_client = UpdatingLambdaClient(package_hash(b"old deployed code"))
    for target, name, value in (
      (globals, "config", {"digital_twin_name": "dt"}),
      (globals, "config_iot_devices", []),
      (globals, "core_lfs_path", str(self.folder / "core")),
      (globals, "aws_lambda_client", self.lambda_client),
      (globals, "aws_iam_client", self.iam),
      (globals, "aws_dynamodb_client", StubAwsClient()),
      (globals, "aws_twinmaker_client", StubAwsClient()),
      (globals, "aws_sts_client", StubStsClient()),
      (deployment_state, "last_applied_config", {"digital_twin_name": "dt"}),
      (CoreAllDeployer, "LAYERS", [("core_l3_hot", L3HotDeployer)]),
    ):
      patcher = patch.object(target, name, value)
      patcher.start()
      self.addCleanup(patcher.stop)
    for patcher in (
      patch.object(globals, "config_hierarchy", {}, create=True),
      patch.dict(os.environ, {deployment_state.STATE_DIR_ENV: str(self.folder / "state")}),
      patch("time.sleep"),
    ):
      patcher.start()
      self.addCleanup(patcher.stop)

  def make_plan(self):
    # Reverse the actions to verify that apply restores prerequisite order.
    return [{"group": "core", "layers": [{
      "layer": "core_l3_hot",
      "actions": [
        HotReaderLambdaFunctionDeployer().plan()[0],
        HotReaderIamRoleDeployer().plan()[0],
      ],
    }]}]

  def test_apply_updates_role_before_code_and_records_both_actions(self):
    plan = self.make_plan()
    deployment_state.save_plan(plan)
    original_arn = self.lambda_client.configuration["FunctionArn"]
    events = []
    put_policy = self.iam.put_role_policy
    update_code = self.lambda_client.update_function_code

    def record_policy(**kwargs):
      events.append("policy")
      return put_policy(**kwargs)

    def record_code(**kwargs):
      events.append("code")
      return update_code(**kwargs)

    with patch.object(self.iam, "put_role_policy", side_effect=record_policy), patch.object(
      self.lambda_client, "update_function_code", side_effect=record_code,
    ):
      AllDeployer().apply(plan)

    self.assertEqual(["policy", "code"], events)
    self.assertEqual(original_arn, self.lambda_client.configuration["FunctionArn"])
    self.assertEqual([], self.lambda_client.create_calls)
    self.assertEqual([], self.lambda_client.delete_calls)
    actions = deployment_state.load_plan()[0]["layers"][0]["actions"]
    self.assertTrue(all(action["processed"] for action in actions))
    self.assertEqual("NO_CHANGE", HotReaderLambdaFunctionDeployer().plan()[0]["action"])
    self.assertEqual("NO_CHANGE", HotReaderIamRoleDeployer().plan()[0]["action"])

  def assert_rejected_before_any_group(self, plan):
    with patch.object(AllDeployer, "_apply_group") as apply_group:
      with self.assertRaises(ValueError):
        AllDeployer().apply(plan)
      apply_group.assert_not_called()
    self.assertEqual([], self.lambda_client.update_calls)

  def test_stale_source_is_rejected_before_any_group_mutation(self):
    plan = self.make_plan()
    self.source.write_bytes(b"changed = True\n")

    self.assert_rejected_before_any_group(plan)

  def test_no_change_code_is_also_checked_before_applying_other_resources(self):
    self.lambda_client.configuration["CodeSha256"] = package_hash(
      HotReaderLambdaFunctionDeployer()._code_package(),
    )
    plan = self.make_plan()
    self.assertEqual("NO_CHANGE", plan[0]["layers"][0]["actions"][0]["action"])
    self.source.write_bytes(b"changed = True\n")

    self.assert_rejected_before_any_group(plan)

  def test_missing_update_revision_is_rejected_before_other_mutations(self):
    plan = self.make_plan()
    del plan[0]["layers"][0]["actions"][0]["revision_id"]

    self.assert_rejected_before_any_group(plan)

  def test_remote_code_change_after_no_change_plan_is_rejected(self):
    self.lambda_client.configuration["CodeSha256"] = package_hash(
      HotReaderLambdaFunctionDeployer()._code_package(),
    )
    plan = self.make_plan()
    self.assertEqual("NO_CHANGE", plan[0]["layers"][0]["actions"][0]["action"])
    self.lambda_client.configuration["CodeSha256"] = package_hash(b"remote old code")

    self.assert_rejected_before_any_group(plan)

  def test_remote_revision_change_is_rejected_before_prerequisite_updates(self):
    plan = self.make_plan()
    self.lambda_client.configuration["RevisionId"] = "concurrent-revision"

    self.assert_rejected_before_any_group(plan)

  def test_changed_twin_name_is_rejected_before_other_mutations(self):
    plan = self.make_plan()
    globals.config = {"digital_twin_name": "another-twin"}

    self.assert_rejected_before_any_group(plan)


if __name__ == "__main__":
  unittest.main()
