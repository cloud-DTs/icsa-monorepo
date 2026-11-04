from __future__ import annotations
import unittest
from src.validation import config_iot_devices
from validation_helpers import clone, valid_config_iot_devices


class ConfigIotDevicesValidationTests(unittest.TestCase):
  def test_valid_config_iot_devices_passes(self) -> None:
    config_iot_devices.validate(valid_config_iot_devices())

  def test_duplicate_device_id_fails(self) -> None:
    value = valid_config_iot_devices()
    value.append(clone(value[0]))

    with self.assertRaisesRegex(ValueError, "duplicated"):
      config_iot_devices.validate(value)

  def test_reserved_property_name_fails(self) -> None:
    value = valid_config_iot_devices()
    value[0]["properties"][0]["name"] = "time"

    with self.assertRaisesRegex(ValueError, "reserved property name"):
      config_iot_devices.validate(value)

  def test_unsupported_data_type_fails(self) -> None:
    value = valid_config_iot_devices()
    value[0]["properties"][0]["dataType"] = "MAP"

    with self.assertRaisesRegex(ValueError, "must be one of"):
      config_iot_devices.validate(value)

  def test_init_value_type_mismatch_fails(self) -> None:
    value = valid_config_iot_devices()
    value[0]["properties"][1]["initValue"] = "80"

    with self.assertRaisesRegex(ValueError, "must be an integer"):
      config_iot_devices.validate(value)

  def test_vector_data_type_and_init_value_pass(self) -> None:
    value = valid_config_iot_devices()
    value[0]["properties"].append(
      {
        "name": "samples",
        "dataType": "VECTOR_DOUBLE",
        "initValue": [1, 2.5],
      }
    )

    config_iot_devices.validate(value)

  def test_vector_init_value_element_type_mismatch_fails(self) -> None:
    value = valid_config_iot_devices()
    value[0]["properties"].append(
      {
        "name": "samples",
        "dataType": "VECTOR_INTEGER",
        "initValue": [1, "2"],
      }
    )

    with self.assertRaisesRegex(ValueError, r"initValue\[1\].*integer"):
      config_iot_devices.validate(value)


if __name__ == "__main__":
  unittest.main()
