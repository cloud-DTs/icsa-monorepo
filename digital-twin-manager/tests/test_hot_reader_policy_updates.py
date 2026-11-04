from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tests.aws_stubs import ClientError, StubAwsClient, StubStsClient, install_aws_stubs

install_aws_stubs()

import deployment_state
import globals
from deployers.aws.core.hot_reader_iam_role import HotReaderIamRoleDeployer


class PolicyIamClient:
  def __init__(self):
    self.policy = {"Version": "2012-10-17", "Statement": []}
    self.lookup_error = None
    self.role_arn = "arn:aws:iam::123456789012:role/dt-hot-reader"

  def get_role(self, **kwargs):
    if self.lookup_error:
      raise self.lookup_error
    return {"Role": {"Arn": self.role_arn}}

  def get_role_policy(self, **kwargs):
    if self.policy is None:
      raise ClientError({"Error": {"Code": "NoSuchEntity"}}, "GetRolePolicy")
    return {"PolicyDocument": self.policy}

  def put_role_policy(self, **kwargs):
    self.policy = json.loads(kwargs["PolicyDocument"])


class HotReaderPolicyUpdateTests(unittest.TestCase):
  def setUp(self):
    self.client = PolicyIamClient()
    for target, name, value in (
      (globals, "config", {"digital_twin_name": "dt"}),
      (globals, "aws_iam_client", self.client),
      (globals, "aws_dynamodb_client", StubAwsClient()),
      (globals, "aws_twinmaker_client", StubAwsClient()),
      (globals, "aws_sts_client", StubStsClient()),
      (deployment_state, "last_applied_config", {"digital_twin_name": "dt"}),
    ):
      patcher = patch.object(target, name, value)
      patcher.start()
      self.addCleanup(patcher.stop)
    sleep = patch("time.sleep")
    sleep.start()
    self.addCleanup(sleep.stop)
    self.deployer = HotReaderIamRoleDeployer()

  def test_existing_role_gets_schema_permission_without_replacement(self):
    original_arn = self.client.role_arn
    action = self.deployer.plan()[0]
    self.assertEqual("UPDATE", action["action"])

    self.deployer.apply(action, action["resource"])

    actions = [
      action
      for statement in self.client.policy["Statement"]
      for action in ([statement["Action"]] if isinstance(statement["Action"], str) else statement["Action"])
    ]
    self.assertIn("iottwinmaker:GetComponentType", actions)
    self.assertIn("iottwinmaker:GetEntity", actions)
    self.assertIn("dynamodb:Query", actions)
    self.assertEqual(original_arn, self.client.role_arn)
    self.assertEqual("NO_CHANGE", self.deployer.plan()[0]["action"])

  def test_missing_inline_policy_is_added_to_existing_role(self):
    self.client.policy = None

    action = self.deployer.plan()[0]

    self.assertEqual("UPDATE", action["action"])
    self.deployer.apply(action, action["resource"])
    self.assertEqual("NO_CHANGE", self.deployer.plan()[0]["action"])

  def test_access_denied_is_not_treated_as_absent_role(self):
    self.client.lookup_error = ClientError({"Error": {"Code": "AccessDenied"}}, "GetRole")

    with self.assertRaises(ClientError):
      self.deployer.plan()


if __name__ == "__main__":
  unittest.main()
