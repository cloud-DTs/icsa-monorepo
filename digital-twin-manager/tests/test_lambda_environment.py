from __future__ import annotations

import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import StubStsClient, install_aws_stubs

install_aws_stubs()

import globals
import util
from deployers.aws.core.dispatcher_lambda_function import (
  DispatcherLambdaFunctionDeployer,
)
from deployers.aws.core.event_checker_lambda_function import (
  EventCheckerLambdaFunctionDeployer,
)
from deployers.aws.core.hot_cold_mover_lambda_function import (
  HotColdMoverLambdaFunctionDeployer,
)


class RecordingIamClient:
  def get_role(self, RoleName):
    return {"Role": {"Arn": f"arn:aws:iam::123456789012:role/{RoleName}"}}


class RecordingLambdaClient:
  def __init__(self):
    self.meta = types.SimpleNamespace(region_name="eu-west-1")
    self.create_function_calls = []

  def create_function(self, **kwargs):
    self.create_function_calls.append(kwargs)
    return {"FunctionArn": f"arn:aws:lambda:eu-west-1:123456789012:function:{kwargs['FunctionName']}"}

  def get_function(self, FunctionName):
    return {
      "Configuration": {
        "FunctionArn": f"arn:aws:lambda:eu-west-1:123456789012:function:{FunctionName}"
      }
    }


class LambdaEnvironmentTests(unittest.TestCase):
  def setUp(self) -> None:
    self.original_globals = {
      "config": globals.config,
      "config_iot_devices": globals.config_iot_devices,
      "config_events": getattr(globals, "config_events", []),
      "aws_iam_client": globals.aws_iam_client,
      "aws_lambda_client": globals.aws_lambda_client,
      "aws_sts_client": globals.aws_sts_client,
    }

    globals.config = {
      "digital_twin_name": "dtc-y-01",
      "hot_storage_size_in_days": 30,
      "cold_storage_size_in_days": 60,
    }
    globals.config_iot_devices = []
    globals.config_events = []
    globals.aws_iam_client = RecordingIamClient()
    globals.aws_lambda_client = RecordingLambdaClient()
    globals.aws_sts_client = StubStsClient()

  def tearDown(self) -> None:
    for name, value in self.original_globals.items():
      setattr(globals, name, value)

  def test_environment_at_aws_limit_is_accepted(self) -> None:
    environment = util.lambda_environment({"A": "x" * 4095})

    self.assertEqual(4095, len(environment["Variables"]["A"]))

  def test_environment_over_aws_limit_fails_before_api_call(self) -> None:
    with self.assertRaisesRegex(ValueError, "4097 bytes"):
      util.lambda_environment({"A": "x" * 4096})

  def test_environment_values_must_be_strings(self) -> None:
    with self.assertRaisesRegex(TypeError, "must be strings"):
      util.lambda_environment({"RETENTION_DAYS": 30})

  def test_compile_lambda_function_can_add_generated_config(self) -> None:
    with tempfile.TemporaryDirectory() as lambda_dir:
      Path(lambda_dir, "lambda_function.py").write_text(
        "def lambda_handler(event, context):\n  return event\n",
        encoding="utf-8",
      )

      zip_bytes = util.compile_lambda_function(
        lambda_dir,
        extra_files={"generated.json": '{"enabled":true}'},
      )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
      self.assertEqual(
        {"lambda_function.py", "generated.json"},
        set(archive.namelist()),
      )
      self.assertEqual(
        {"enabled": True},
        json.loads(archive.read("generated.json")),
      )

  def test_dispatcher_uses_raw_digital_twin_name_only(self) -> None:
    configuration = DispatcherLambdaFunctionDeployer()._desired_function_configuration()

    self.assertEqual(
      {"DIGITAL_TWIN_NAME": "dtc-y-01"},
      configuration["Environment"]["Variables"],
    )

  def test_large_event_config_is_bundled_instead_of_environment(self) -> None:
    globals.config_events = [
      {
        "condition": f"entity.component.property{index} > INTEGER({index})",
        "action": {
          "type": "lambda",
          "functionName": f"action-{index}",
          "external": True,
        },
      }
      for index in range(200)
    ]
    self.assertGreater(len(json.dumps(globals.config_events).encode("utf-8")), 4096)

    EventCheckerLambdaFunctionDeployer().deploy()

    request = globals.aws_lambda_client.create_function_calls[-1]
    variables = request["Environment"]["Variables"]
    self.assertNotIn("DIGITAL_TWIN_INFO", variables)
    self.assertEqual("dtc-y-01", variables["DIGITAL_TWIN_NAME"])

    with zipfile.ZipFile(io.BytesIO(request["Code"]["ZipFile"])) as archive:
      bundled_events = json.loads(archive.read("config_events.json"))

    self.assertEqual(globals.config_events, bundled_events)

  def test_large_device_list_is_bundled_instead_of_environment(self) -> None:
    globals.config_iot_devices = [
      {"id": f"device-{index:04d}", "properties": []}
      for index in reversed(range(1000))
    ]
    expected_ids = sorted(device["id"] for device in globals.config_iot_devices)
    self.assertGreater(len(json.dumps(expected_ids).encode("utf-8")), 4096)

    HotColdMoverLambdaFunctionDeployer().deploy()

    request = globals.aws_lambda_client.create_function_calls[-1]
    variables = request["Environment"]["Variables"]
    self.assertNotIn("DIGITAL_TWIN_INFO", variables)
    self.assertEqual("30", variables["HOT_STORAGE_SIZE_IN_DAYS"])

    with zipfile.ZipFile(io.BytesIO(request["Code"]["ZipFile"])) as archive:
      bundled_ids = json.loads(archive.read("iot_device_ids.json"))

    self.assertEqual(expected_ids, bundled_ids)

  def test_aws_lambda_code_does_not_reference_full_digital_twin_info(self) -> None:
    source_roots = [
      REPO_ROOT / "src" / "deployers" / "aws",
      REPO_ROOT / "lambda_functions",
    ]

    for source_root in source_roots:
      for path in source_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("DIGITAL_TWIN_INFO", source, str(path))


if __name__ == "__main__":
  unittest.main()
