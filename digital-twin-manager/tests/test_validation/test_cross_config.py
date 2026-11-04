from __future__ import annotations
import unittest
from src.validation import cross_config
from validation_helpers import clone, valid_config_set


class CrossConfigValidationTests(unittest.TestCase):
  def test_valid_config_set_passes(self) -> None:
    configs = valid_config_set()

    cross_config.validate(
      configs["config_providers"],
      configs["config_iot_devices"],
      configs["config_hierarchy"],
      configs["config_events"],
    )

  def test_hierarchy_unknown_iot_device_fails(self) -> None:
    configs = valid_config_set()
    configs["config_hierarchy"][0]["children"][0]["iotDeviceId"] = "missing"

    with self.assertRaisesRegex(ValueError, "references unknown"):
      self._validate(configs)

  def test_event_unknown_entity_fails(self) -> None:
    configs = valid_config_set()
    configs["config_events"][0]["condition"] = (
      "missing.temperatureSensor.temperature > INTEGER(80)"
    )

    with self.assertRaisesRegex(ValueError, "unknown config_hierarchy.json entity"):
      self._validate(configs)

  def test_event_unknown_component_fails(self) -> None:
    configs = valid_config_set()
    configs["config_events"][0]["condition"] = (
      "room-1.missing.temperature > INTEGER(80)"
    )

    with self.assertRaisesRegex(ValueError, "unknown component"):
      self._validate(configs)

  def test_event_unknown_property_fails(self) -> None:
    configs = valid_config_set()
    configs["config_events"][0]["condition"] = (
      "room-1.temperatureSensor.missing > INTEGER(80)"
    )

    with self.assertRaisesRegex(ValueError, "unknown property"):
      self._validate(configs)

  def test_feedback_unknown_iot_device_fails(self) -> None:
    configs = valid_config_set()
    configs["config_events"][0]["action"]["feedback"]["iotDeviceId"] = "missing"

    with self.assertRaisesRegex(ValueError, "action.feedback.iotDeviceId"):
      self._validate(configs)

  def test_input_parameter_unknown_property_fails(self) -> None:
    configs = valid_config_set()
    parameter = configs["config_events"][0]["action"]["inputParameters"][0]
    parameter["id"] = "room-1.temperatureSensor.missing"

    with self.assertRaisesRegex(ValueError, "inputParameters.*unknown property"):
      self._validate(configs)

  def test_input_parameter_data_type_mismatch_fails(self) -> None:
    configs = valid_config_set()
    parameter = configs["config_events"][0]["action"]["inputParameters"][0]
    parameter["dataType"] = "DOUBLE"

    with self.assertRaisesRegex(ValueError, "referenced property dataType"):
      self._validate(configs)

  def test_provider_incompatibility_fails(self) -> None:
    configs = valid_config_set()
    configs["config_providers"] = clone(configs["config_providers"])
    configs["config_providers"]["layer_4_provider"] = "local"

    with self.assertRaisesRegex(ValueError, "requires"):
      self._validate(configs)

  def _validate(self, configs) -> None:
    cross_config.validate(
      configs["config_providers"],
      configs["config_iot_devices"],
      configs["config_hierarchy"],
      configs["config_events"],
    )


if __name__ == "__main__":
  unittest.main()
