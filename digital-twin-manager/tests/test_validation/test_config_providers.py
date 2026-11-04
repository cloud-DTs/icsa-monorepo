from __future__ import annotations
import unittest
from src.validation import config_providers
from validation_helpers import valid_config_providers


class ConfigProvidersValidationTests(unittest.TestCase):
  def test_valid_config_providers_passes(self) -> None:
    config_providers.validate(valid_config_providers())

  def test_missing_provider_key_fails(self) -> None:
    value = valid_config_providers()
    del value["layer_4_provider"]

    with self.assertRaisesRegex(ValueError, "missing required key"):
      config_providers.validate(value)

  def test_unknown_provider_key_fails(self) -> None:
    value = valid_config_providers()
    value["layer_6_provider"] = "aws"

    with self.assertRaisesRegex(ValueError, "unknown key"):
      config_providers.validate(value)

  def test_unsupported_provider_fails(self) -> None:
    value = valid_config_providers()
    value["layer_4_provider"] = "local"

    with self.assertRaisesRegex(ValueError, "must be one of"):
      config_providers.validate(value)


if __name__ == "__main__":
  unittest.main()
