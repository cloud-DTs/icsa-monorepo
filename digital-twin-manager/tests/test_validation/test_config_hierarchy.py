from __future__ import annotations
import unittest
from src.validation import config_hierarchy
from validation_helpers import clone, valid_config_hierarchy


class ConfigHierarchyValidationTests(unittest.TestCase):
  def test_valid_config_hierarchy_passes(self) -> None:
    config_hierarchy.validate(valid_config_hierarchy())

  def test_root_component_fails(self) -> None:
    value = [
      {
        "type": "component",
        "name": "temperatureSensor",
        "iotDeviceId": "sensor-1",
      }
    ]

    with self.assertRaisesRegex(ValueError, "must be one of"):
      config_hierarchy.validate(value)

  def test_component_without_source_fails(self) -> None:
    value = valid_config_hierarchy()
    del value[0]["children"][0]["iotDeviceId"]

    with self.assertRaisesRegex(ValueError, "at least one"):
      config_hierarchy.validate(value)

  def test_component_with_component_type_id_only_passes(self) -> None:
    value = valid_config_hierarchy()
    del value[0]["children"][0]["iotDeviceId"]
    value[0]["children"][0]["componentTypeId"] = "shared-sensor-type"

    config_hierarchy.validate(value)

  def test_component_with_both_sources_passes(self) -> None:
    value = valid_config_hierarchy()
    value[0]["children"][0]["componentTypeId"] = "shared-sensor-type"

    config_hierarchy.validate(value)

  def test_component_with_component_type_name_passes(self) -> None:
    sources = [
      {"iotDeviceId": "sensor-1"},
      {"componentTypeId": "shared-sensor-type"},
      {"iotDeviceId": "sensor-1", "componentTypeId": "shared-sensor-type"},
    ]
    for source in sources:
      with self.subTest(source=source):
        value = valid_config_hierarchy()
        component = value[0]["children"][0]
        del component["iotDeviceId"]
        component.update(source)
        component["componentTypeName"] = "PAC Sensor v2.0"
        value[0]["children"][1]["children"][0]["componentTypeName"] = "Humidity Sensor"

        config_hierarchy.validate(value)

  def test_non_string_component_type_name_fails(self) -> None:
    for name in (None, 123, True, [], {}):
      with self.subTest(name=name):
        value = valid_config_hierarchy()
        value[0]["children"][0]["componentTypeName"] = name

        with self.assertRaisesRegex(ValueError, r"componentTypeName must be a string"):
          config_hierarchy.validate(value)

  def test_empty_component_type_name_fails(self) -> None:
    value = valid_config_hierarchy()
    value[0]["children"][0]["componentTypeName"] = ""

    with self.assertRaisesRegex(ValueError, r"componentTypeName must not be empty"):
      config_hierarchy.validate(value)

  def test_component_type_name_does_not_replace_source(self) -> None:
    value = valid_config_hierarchy()
    del value[0]["children"][0]["iotDeviceId"]
    value[0]["children"][0]["componentTypeName"] = "PAC Sensor"

    with self.assertRaisesRegex(ValueError, "at least one"):
      config_hierarchy.validate(value)

  def test_unknown_component_key_still_fails(self) -> None:
    value = valid_config_hierarchy()
    value[0]["children"][0]["componentTypeName"] = "PAC Sensor"
    value[0]["children"][0]["unexpected"] = "value"

    with self.assertRaisesRegex(ValueError, r"contains unknown key\(s\): unexpected$"):
      config_hierarchy.validate(value)

  def test_duplicate_entity_id_fails(self) -> None:
    value = valid_config_hierarchy()
    duplicate_entity = clone(value[0]["children"][1])
    duplicate_entity["id"] = "room-1"
    value[0]["children"].append(duplicate_entity)

    with self.assertRaisesRegex(ValueError, "duplicated"):
      config_hierarchy.validate(value)

  def test_duplicate_component_name_in_same_entity_fails(self) -> None:
    value = valid_config_hierarchy()
    duplicate_component = clone(value[0]["children"][0])
    value[0]["children"].append(duplicate_component)

    with self.assertRaisesRegex(ValueError, "duplicated in the same entity"):
      config_hierarchy.validate(value)


if __name__ == "__main__":
  unittest.main()
