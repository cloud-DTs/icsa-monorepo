from __future__ import annotations
import unittest
from src.validation import config_events
from validation_helpers import clone, valid_config_events


class ConfigEventsValidationTests(unittest.TestCase):
  def test_valid_config_events_passes(self) -> None:
    config_events.validate(valid_config_events())

  def test_condition_without_required_spaces_fails(self) -> None:
    value = valid_config_events()
    value[0]["condition"] = "room-1.temperatureSensor.temperature>INTEGER(80)"

    with self.assertRaisesRegex(ValueError, "must have format"):
      config_events.validate(value)

  def test_unsupported_action_type_fails(self) -> None:
    value = valid_config_events()
    value[0]["action"]["type"] = "sns"

    with self.assertRaisesRegex(ValueError, "must be one of"):
      config_events.validate(value)

  def test_path_to_code_with_external_action_fails(self) -> None:
    value = valid_config_events()
    value[0]["action"]["pathToCode"] = "lambda_functions/event_actions/alert"

    with self.assertRaisesRegex(ValueError, "only valid when external is false"):
      config_events.validate(value)

  def test_feedback_without_single_target_fails(self) -> None:
    value = valid_config_events()
    value[0]["action"]["feedback"]["topic"] = "alerts"

    with self.assertRaisesRegex(ValueError, "exactly one"):
      config_events.validate(value)

  def test_duplicate_internal_function_name_fails(self) -> None:
    value = [
      {
        "condition": "room-1.temperatureSensor.temperature > INTEGER(80)",
        "action": {
          "type": "lambda",
          "functionName": "alertAction",
          "external": False,
        },
      },
      {
        "condition": "room-1.temperatureSensor.temperature == INTEGER(80)",
        "action": {
          "type": "lambda",
          "functionName": "alertAction",
          "external": False,
        },
      },
    ]

    with self.assertRaisesRegex(ValueError, "duplicates another internal"):
      config_events.validate(value)

  def test_input_parameter_requires_id_or_value(self) -> None:
    value = valid_config_events()
    del value[0]["action"]["inputParameters"][0]["id"]
    del value[0]["action"]["inputParameters"][0]["value"]

    with self.assertRaisesRegex(ValueError, "at least one of"):
      config_events.validate(value)

  def test_input_parameter_value_must_match_data_type(self) -> None:
    value = valid_config_events()
    value[0]["action"]["inputParameters"][0]["value"] = "80"

    with self.assertRaisesRegex(ValueError, "must be an integer"):
      config_events.validate(value)

  def test_input_parameter_with_value_only_passes(self) -> None:
    value = valid_config_events()
    del value[0]["action"]["inputParameters"][0]["id"]

    config_events.validate(value)

  def test_duplicate_output_parameter_name_fails(self) -> None:
    value = valid_config_events()
    value[0]["action"]["outputParameters"].append(
      clone(value[0]["action"]["outputParameters"][0])
    )

    with self.assertRaisesRegex(ValueError, "is duplicated"):
      config_events.validate(value)

  def test_vector_parameter_value_passes(self) -> None:
    value = valid_config_events()
    value[0]["action"]["inputParameters"] = [
      {
        "name": "samples",
        "dataType": "VECTOR_DOUBLE",
        "value": [1, 2.5],
      },
    ]

    config_events.validate(value)

  def test_decimal_typed_constant_fails_current_runtime_parser(self) -> None:
    value = clone(valid_config_events())
    value[0]["condition"] = "room-1.temperatureSensor.temperature > DOUBLE(80.5)"

    with self.assertRaisesRegex(ValueError, "typed constant"):
      config_events.validate(value)


if __name__ == "__main__":
  unittest.main()
