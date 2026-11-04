from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import StubAwsClient, StubStsClient, install_aws_stubs

install_aws_stubs()

import globals
from deployers.aws.core.hot_reader_lambda_function import HotReaderLambdaFunctionDeployer
from deployers.aws.lambda_function import plan_lambda


class RecordingLambdaClient(StubAwsClient):
  def __init__(self):
    super().__init__()
    self.create_function_calls = []
    self.add_permission_calls = []

  def create_function(self, **kwargs):
    self.create_function_calls.append(kwargs)

  def add_permission(self, **kwargs):
    self.add_permission_calls.append(kwargs)


class RoleIamClient:
  def get_role(self, RoleName):
    return {"Role": {"Arn": f"arn:aws:iam::123456789012:role/{RoleName}"}}


class HotReaderLambdaPermissionTests(unittest.TestCase):
  def setUp(self) -> None:
    self.original_globals = {
      name: getattr(globals, name, None)
      for name in ("config", "aws_iam_client", "aws_lambda_client", "aws_sts_client")
    }

    globals.config = {
      "digital_twin_name": "dtc-y-01",
      "hot_storage_size_in_days": 30,
      "cold_storage_size_in_days": 60,
    }
    globals.aws_iam_client = RoleIamClient()
    globals.aws_lambda_client = RecordingLambdaClient()
    globals.aws_sts_client = StubStsClient()

    patcher = patch("util.compile_reproducible_lambda_function", return_value=b"zip")
    self.compile_package = patcher.start()
    self.addCleanup(patcher.stop)

  def tearDown(self) -> None:
    for name, value in self.original_globals.items():
      setattr(globals, name, value)

  def test_twinmaker_invoke_permission_is_limited_to_this_account(self) -> None:
    HotReaderLambdaFunctionDeployer().deploy()

    calls = globals.aws_lambda_client.add_permission_calls
    self.assertEqual(len(calls), 1)
    self.assertEqual(calls[0]["FunctionName"], globals.hot_reader_lambda_function_name())
    self.assertEqual(calls[0]["StatementId"], "AllowTwinmakerInvoke")
    self.assertEqual(calls[0]["Principal"], "iottwinmaker.amazonaws.com")
    self.assertEqual(calls[0]["Action"], "lambda:InvokeFunction")
    self.assertEqual(calls[0]["SourceAccount"], "123456789012")
    self.assertEqual(globals.aws_lambda_client.create_function_calls[0]["Code"], {"ZipFile": b"zip"})
    self.compile_package.assert_called_once()

  def test_explicit_function_and_role_names_keep_the_scoped_permission(self) -> None:
    HotReaderLambdaFunctionDeployer().deploy(
      function_name="custom-hot-reader",
      role_name="custom-reader-role",
      zip_code=b"planned zip",
    )

    create_call = globals.aws_lambda_client.create_function_calls[0]
    self.assertEqual(create_call["FunctionName"], "custom-hot-reader")
    self.assertEqual(create_call["Role"], "arn:aws:iam::123456789012:role/custom-reader-role")
    self.assertEqual(create_call["Code"], {"ZipFile": b"planned zip"})
    self.assertEqual(len(globals.aws_lambda_client.add_permission_calls), 1)
    permission = globals.aws_lambda_client.add_permission_calls[0]
    self.assertEqual(permission["FunctionName"], "custom-hot-reader")
    self.assertEqual(permission["SourceAccount"], "123456789012")
    self.compile_package.assert_not_called()

  def test_permission_uses_the_deploying_account(self) -> None:
    with patch.object(globals.aws_sts_client, "get_caller_identity", return_value={"Account": "210987654321"}):
      HotReaderLambdaFunctionDeployer().deploy(zip_code=b"planned zip")

    permission = globals.aws_lambda_client.add_permission_calls[0]
    self.assertEqual(permission["SourceAccount"], "210987654321")

  def test_apply_deploy_adds_the_account_condition(self) -> None:
    deployer = HotReaderLambdaFunctionDeployer()
    action = plan_lambda(deployer._lambda_definition(), None)[0]

    deployer.apply(action, action["resource"])

    self.assertEqual(len(globals.aws_lambda_client.create_function_calls), 1)
    self.assertEqual(len(globals.aws_lambda_client.add_permission_calls), 1)
    permission = globals.aws_lambda_client.add_permission_calls[0]
    self.assertEqual(permission["FunctionName"], action["resource"])
    self.assertEqual(permission["SourceAccount"], "123456789012")


if __name__ == "__main__":
  unittest.main()
