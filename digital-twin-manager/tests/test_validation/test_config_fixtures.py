from __future__ import annotations

import json
import unittest
from pathlib import Path

import src.validation as validation


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_CONFIGS_DIR = REPO_ROOT / "configs" / "validation"


def load_config_set(case_name: str):
  case_dir = VALIDATION_CONFIGS_DIR / case_name

  return {
    "config": read_json(case_dir / "config.json"),
    "config_credentials": read_json(case_dir / "config_credentials.json"),
    "config_events": read_json(case_dir / "config_events.json"),
    "config_hierarchy": read_json(case_dir / "config_hierarchy.json"),
    "config_iot_devices": read_json(case_dir / "config_iot_devices.json"),
    "config_providers": read_json(case_dir / "config_providers.json"),
  }


def read_json(path: Path):
  with open(path, "r", encoding="utf-8") as file:
    return json.load(file)


def validate_config_set(configs) -> None:
  validation.validate_all_configs(
    configs["config"],
    configs["config_credentials"],
    configs["config_events"],
    configs["config_hierarchy"],
    configs["config_iot_devices"],
    configs["config_providers"],
  )


class ValidationConfigFixtureTests(unittest.TestCase):
  def test_valid_fixture_passes_validate_all_configs(self) -> None:
    validate_config_set(load_config_set("valid"))

  def test_invalid_config_type_fixtures_fail_validate_all_configs(self) -> None:
    invalid_cases = [
      ("invalid-config", "digital_twin_name"),
      ("invalid-config-credentials", "aws_region"),
      ("invalid-config-events", "operator"),
      ("invalid-config-hierarchy", r"config_hierarchy.json\[0\].type"),
      ("invalid-config-iot-devices", "duplicated"),
      ("invalid-config-providers", "must be one of"),
    ]

    for case_name, error_pattern in invalid_cases:
      with self.subTest(case_name=case_name):
        with self.assertRaisesRegex(ValueError, error_pattern):
          validate_config_set(load_config_set(case_name))

  def test_invalid_event_reference_fixture_fails_validate_all_configs(self) -> None:
    with self.assertRaisesRegex(ValueError, "unknown property"):
      validate_config_set(load_config_set("invalid-event-reference"))


if __name__ == "__main__":
  unittest.main()
