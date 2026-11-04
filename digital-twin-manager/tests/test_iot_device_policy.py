from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_shared_iot_policy import StatefulIotClient

import globals
import deployment_state
from deployers.aws.iot.iot_thing import IotThingDeployer


class IotDevicePolicyTests(unittest.TestCase):
  def setUp(self):
    self.iot = StatefulIotClient()
    self.tmp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp_dir.cleanup)
    self.auth_path = Path(self.tmp_dir.name) / "dtc-y-01"
    for patcher in (
      patch.object(globals, "config", {"digital_twin_name": "dtc-y-01"}),
      patch.object(globals, "config_events", [], create=True),
      patch.object(globals, "aws_iot_client", self.iot),
      patch.object(globals, "aws_sts_client", SimpleNamespace(get_caller_identity=lambda: {"Account": "123456789012"})),
      patch.object(globals, "iot_data_path", str(self.auth_path)),
      patch.object(deployment_state, "last_applied_config", {"digital_twin_name": "dtc-y-01"}),
      patch.object(deployment_state, "last_applied_config_events", []),
    ):
      patcher.start()
      self.addCleanup(patcher.stop)
    self.deployer = IotThingDeployer()

  def test_devices_in_different_twins_use_separate_shared_policies(self):
    device = {"id": "device-1"}
    self.deployer.deploy(device)

    globals.config = {"digital_twin_name": "dtc-y-02"}
    globals.iot_data_path = str(Path(self.tmp_dir.name) / "dtc-y-02")
    self.deployer.deploy(device)

    self.assertEqual({"dtc-y-01-iot-policy", "dtc-y-02-iot-policy"}, set(self.iot.policies))
    for twin in ("dtc-y-01", "dtc-y-02"):
      principals = self.iot.things[f"{twin}-device-1"]
      self.assertEqual(1, len(principals))
      for principal in principals:
        self.assertEqual({f"{twin}-iot-policy"}, self.iot.attachments[principal])
    self.assertEqual(2, len(self.iot.certificates))

  def test_feedback_changes_reuse_shared_policy_and_existing_certificate(self):
    self.deployer.deploy({"id": "device-1"})
    policy_before = copy.deepcopy(self.iot.policies)
    principal_before = set(self.iot.things["dtc-y-01-device-1"])
    auth_before = {
      path: path.read_bytes() for path in self.auth_path.rglob("*") if path.is_file()
    }

    globals.config_events = [
      {"action": {"feedback": {"type": "mqtt", "topic": "custom-feedback"}}},
      {"action": {"feedback": {"type": "mqtt", "iotDeviceId": "device-2"}}},
    ]
    self.deployer.deploy({"id": "device-1"})
    self.deployer.deploy({"id": "device-2"})

    self.assertEqual(set(policy_before), set(self.iot.policies))
    self.assertNotEqual(policy_before, self.iot.policies)
    self.assertIn("custom-feedback", str(self.iot.policies))
    self.assertEqual(principal_before, self.iot.things["dtc-y-01-device-1"])
    self.assertEqual(2, len(self.iot.certificates))
    for principal in self.iot.certificates:
      self.assertEqual({"dtc-y-01-iot-policy"}, self.iot.attachments[principal])
    for path, content in auth_before.items():
      self.assertEqual(content, path.read_bytes())


if __name__ == "__main__":
  unittest.main()
