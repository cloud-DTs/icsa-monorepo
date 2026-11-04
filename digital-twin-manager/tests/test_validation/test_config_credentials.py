from __future__ import annotations
import unittest
from src.validation import config_credentials

from validation_helpers import valid_config_credentials


class ConfigCredentialsValidationTests(unittest.TestCase):
  def test_valid_config_credentials_passes(self) -> None:
    config_credentials.validate(valid_config_credentials())

  def test_short_access_key_id_fails(self) -> None:
    value = valid_config_credentials()
    value["aws_access_key_id"] = "A" * 19

    with self.assertRaisesRegex(ValueError, "20 characters"):
      config_credentials.validate(value)

  def test_invalid_secret_key_format_fails(self) -> None:
    value = valid_config_credentials()
    value["aws_secret_access_key"] = "!" * 40

    with self.assertRaisesRegex(ValueError, "invalid format"):
      config_credentials.validate(value)

  def test_invalid_region_fails(self) -> None:
    value = valid_config_credentials()
    value["aws_region"] = "eucentral1"

    with self.assertRaisesRegex(ValueError, "invalid format"):
      config_credentials.validate(value)


if __name__ == "__main__":
  unittest.main()
