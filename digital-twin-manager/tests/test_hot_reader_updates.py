from __future__ import annotations

import base64
import hashlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import StubStsClient, install_aws_stubs

install_aws_stubs()

from botocore.exceptions import ClientError
import deployment_state
import globals
import util
from deployers.aws.core.hot_reader_lambda_function import (
  HotReaderLambdaFunctionDeployer,
)


def package_hash(package: bytes) -> str:
  return base64.b64encode(hashlib.sha256(package).digest()).decode("ascii")


class UpdatingLambdaClient:
  """AWS boundary that retains function identity while updating its code."""

  def __init__(self, code_sha256: str | None) -> None:
    self.meta = types.SimpleNamespace(region_name="eu-west-1")
    self.configuration = {
      "FunctionName": "dt-hot-reader",
      "FunctionArn": "arn:aws:lambda:eu-west-1:123456789012:function:dt-hot-reader",
      "RevisionId": "planned-revision",
      "State": "Active",
      "LastUpdateStatus": "Successful",
      "Runtime": "python3.13",
      "Handler": "lambda_function.lambda_handler",
      "Role": "arn:aws:iam::123456789012:role/dt-hot-reader",
      "Timeout": 900,
      "MemorySize": 128,
      "Environment": {"Variables": {
        "DIGITAL_TWIN_NAME": "dt",
        "DYNAMODB_TABLE_NAME": "dt-hot-iot-data",
      }},
    }
    if code_sha256 is not None:
      self.configuration["CodeSha256"] = code_sha256
    self.lookup_error = None
    self.wait_error = None
    self.post_update_hash = None
    self.update_calls = []
    self.create_calls = []
    self.delete_calls = []
    self.completed_updates = 0
    self.pending_code = None

  def get_function(self, **kwargs):
    if self.lookup_error:
      raise self.lookup_error
    return {"Configuration": dict(self.configuration)}

  def get_function_configuration(self, **kwargs):
    self._complete_update()
    return dict(self.configuration)

  def update_function_code(self, **kwargs):
    if kwargs.get("RevisionId") != self.configuration["RevisionId"]:
      raise ClientError(
        {"Error": {"Code": "PreconditionFailedException"}},
        "UpdateFunctionCode",
      )
    self.update_calls.append(kwargs)
    self.pending_code = kwargs["ZipFile"]
    self.configuration["LastUpdateStatus"] = "InProgress"
    return dict(self.configuration)

  def _complete_update(self):
    if self.pending_code is None:
      return
    if self.wait_error:
      raise self.wait_error
    self.configuration["CodeSha256"] = (
      self.post_update_hash or package_hash(self.pending_code)
    )
    self.configuration["LastUpdateStatus"] = "Successful"
    self.configuration["RevisionId"] = "updated-revision"
    self.pending_code = None
    self.completed_updates += 1

  def get_waiter(self, name):
    client = self

    class Waiter:
      def wait(self, **kwargs):
        client._complete_update()

    return Waiter()

  def create_function(self, **kwargs):
    self.create_calls.append(kwargs)

  def delete_function(self, **kwargs):
    self.delete_calls.append(kwargs)


class HotReaderCodeUpdateTests(unittest.TestCase):
  def setUp(self) -> None:
    temporary_directory = tempfile.TemporaryDirectory()
    self.addCleanup(temporary_directory.cleanup)
    self.core_directory = Path(temporary_directory.name)
    self.lambda_directory = self.core_directory / "hot-reader"
    self.lambda_directory.mkdir()
    self.source = self.lambda_directory / "lambda_function.py"
    self.source.write_text(
      "def lambda_handler(event, context):\n  return event\n",
      encoding="utf-8",
    )
    self.desired_package = util.compile_reproducible_lambda_function(str(self.lambda_directory))
    self.desired_hash = package_hash(self.desired_package)
    self.client = UpdatingLambdaClient(package_hash(b"old Lambda package"))
    for target, name, value in (
      (globals, "config", {"digital_twin_name": "dt"}),
      (globals, "core_lfs_path", str(self.core_directory)),
      (globals, "aws_lambda_client", self.client),
      (globals, "aws_sts_client", StubStsClient()),
      (deployment_state, "last_applied_config", {"digital_twin_name": "dt"}),
    ):
      patcher = patch.object(target, name, value)
      patcher.start()
      self.addCleanup(patcher.stop)
    self.deployer = HotReaderLambdaFunctionDeployer()

  def planned_update(self):
    actions = self.deployer.plan()
    self.assertEqual(["UPDATE"], [action["action"] for action in actions])
    return actions[0]

  def test_matching_aws_code_hash_needs_no_update(self) -> None:
    self.client.configuration["CodeSha256"] = self.desired_hash

    actions = self.deployer.plan()

    self.assertEqual(["NO_CHANGE"], [action["action"] for action in actions])

  def test_changed_code_hash_plans_in_place_update(self) -> None:
    actions = self.deployer.plan()

    self.assertEqual(["UPDATE"], [action["action"] for action in actions])
    self.assertEqual("dt-hot-reader", actions[0]["resource"])
    self.assertEqual(self.desired_hash, actions[0]["code_sha256"])
    self.assertEqual("planned-revision", actions[0]["revision_id"])

  def test_missing_remote_hash_does_not_silently_keep_old_code(self) -> None:
    del self.client.configuration["CodeSha256"]

    try:
      actions = self.deployer.plan()
    except (ValueError, RuntimeError):
      return

    self.assertEqual(["UPDATE"], [action["action"] for action in actions])

  def test_missing_function_plans_creation(self) -> None:
    self.client.lookup_error = ClientError(
      {"Error": {"Code": "ResourceNotFoundException"}}, "GetFunction"
    )

    actions = self.deployer.plan()

    self.assertEqual(["DEPLOY"], [action["action"] for action in actions])
    self.assertEqual("dt-hot-reader", actions[0]["resource"])

  def test_aws_access_denied_is_not_treated_as_missing_function(self) -> None:
    self.client.lookup_error = ClientError(
      {"Error": {"Code": "AccessDeniedException"}}, "GetFunction"
    )

    with self.assertRaises(ClientError):
      self.deployer.plan()

  def test_apply_updates_code_without_recreating_function(self) -> None:
    original_arn = self.client.configuration["FunctionArn"]
    action = self.planned_update()

    self.deployer.apply(action, action["resource"])

    self.assertEqual(self.desired_hash, self.client.configuration["CodeSha256"])
    self.assertEqual(original_arn, self.client.configuration["FunctionArn"])
    self.assertEqual(1, self.client.completed_updates)
    self.assertEqual("Successful", self.client.configuration["LastUpdateStatus"])
    self.assertEqual(1, len(self.client.update_calls))
    self.assertEqual("planned-revision", self.client.update_calls[0]["RevisionId"])
    self.assertEqual(self.desired_hash, package_hash(self.client.update_calls[0]["ZipFile"]))
    self.assertEqual([], self.client.create_calls)
    self.assertEqual([], self.client.delete_calls)

  def test_apply_rejects_source_changes_after_plan_before_update(self) -> None:
    action = self.planned_update()
    self.source.write_text(
      "def lambda_handler(event, context):\n  return {'changed': True}\n",
      encoding="utf-8",
    )

    with self.assertRaises((ValueError, RuntimeError)):
      self.deployer.apply(action, action["resource"])

    self.assertEqual([], self.client.update_calls)
    self.assertEqual([], self.client.create_calls)
    self.assertEqual([], self.client.delete_calls)

  def test_apply_uses_planned_revision_to_reject_concurrent_aws_change(self) -> None:
    action = self.planned_update()
    self.client.configuration["RevisionId"] = "concurrent-revision"

    with self.assertRaises(ValueError):
      self.deployer.apply(action, action["resource"])

    self.assertEqual([], self.client.update_calls)
    self.assertEqual([], self.client.create_calls)
    self.assertEqual([], self.client.delete_calls)

  def test_failed_aws_update_is_reported(self) -> None:
    action = self.planned_update()
    self.client.wait_error = RuntimeError("Lambda code update failed")

    with self.assertRaises(RuntimeError):
      self.deployer.apply(action, action["resource"])

    self.assertEqual(0, self.client.completed_updates)

  def test_apply_rejects_wrong_hash_after_aws_reports_success(self) -> None:
    action = self.planned_update()
    self.client.post_update_hash = package_hash(b"unexpected deployed package")

    with self.assertRaises((ValueError, RuntimeError)):
      self.deployer.apply(action, action["resource"])


if __name__ == "__main__":
  unittest.main()
