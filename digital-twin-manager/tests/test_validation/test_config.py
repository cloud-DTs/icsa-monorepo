from __future__ import annotations
import unittest
from src.validation import config
from validation_helpers import clone, valid_config


class ConfigValidationTests(unittest.TestCase):
  def test_valid_config_passes(self) -> None:
    config.validate(valid_config())

  def test_missing_required_key_fails(self) -> None:
    value = valid_config()
    del value["digital_twin_name"]

    with self.assertRaisesRegex(ValueError, "missing required key"):
      config.validate(value)

  def test_invalid_digital_twin_name_fails(self) -> None:
    value = valid_config()
    value["digital_twin_name"] = "Twin Name!"

    with self.assertRaisesRegex(ValueError, "must match regex"):
      config.validate(value)

  def test_non_positive_storage_size_fails(self) -> None:
    value = clone(valid_config())
    value["hot_storage_size_in_days"] = 0

    with self.assertRaisesRegex(ValueError, "greater than 0"):
      config.validate(value)


if __name__ == "__main__":
  unittest.main()
