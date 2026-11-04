from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import resource_names


class ResourceNamesTests(unittest.TestCase):
  def setUp(self) -> None:
    self.config = {"digital_twin_name": "dtc-y-01"}
    self.iot_device = {"id": "sensor-1"}

  def test_processor_names_use_device_processor_logical_name(self) -> None:
    self.assertEqual(
      "sensor-1-processor",
      resource_names.processor_logical_name(self.iot_device),
    )
    self.assertEqual(
      "dtc-y-01-sensor-1-processor",
      resource_names.processor_lambda_function_name(self.config, self.iot_device),
    )

  def test_iot_rule_name_replaces_dashes(self) -> None:
    self.assertEqual(
      "dtc_y_01_trigger_dispatcher",
      resource_names.dispatcher_iot_rule_name(self.config),
    )

  def test_iot_policy_is_shared_by_the_twin(self) -> None:
    self.assertEqual("dtc-y-01-iot-policy", resource_names.iot_policy_name(self.config))
    self.assertNotEqual(
      resource_names.iot_policy_name(self.config),
      resource_names.iot_policy_name({"digital_twin_name": "other"}),
    )

  def test_legacy_device_policy_name_is_available_for_migration(self) -> None:
    self.assertEqual(
      "dtc-y-01-sensor-1",
      resource_names.iot_thing_policy_name(self.config, self.iot_device),
    )

  def test_s3_bucket_names_are_lowercase(self) -> None:
    self.assertEqual(
      "dtc-y-01-twinmaker",
      resource_names.twinmaker_s3_bucket_name(self.config),
    )

  def test_event_action_id_is_deterministic(self) -> None:
    event = {
      "condition": "root.component.value > 10",
      "action": {
        "type": "lambda",
        "functionName": "alertAction",
        "external": True,
      },
    }

    first_id = resource_names.event_action_id(event)
    second_id = resource_names.event_action_id(dict(event))

    self.assertEqual(first_id, second_id)
    self.assertTrue(first_id.startswith("lambda:alertAction:"))


if __name__ == "__main__":
  unittest.main()

