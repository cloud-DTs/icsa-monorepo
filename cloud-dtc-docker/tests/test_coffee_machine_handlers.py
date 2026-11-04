import importlib.util
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COFFEE_CODE_ROOT = REPOSITORY_ROOT / "demo-code" / "coffee-machine"
COFFEE_MODEL = (
    REPOSITORY_ROOT
    / "pipeline"
    / "digital-twin-profile-sysml-v2"
    / "input"
    / "CoffeeMachine.sysml"
)


def load_handler(directory_name: str):
    module_path = COFFEE_CODE_ROOT / directory_name / "lambda_function.py"
    module_name = "coffee_machine_" + directory_name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load handler from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event_for(action_name: str, **inputs):
    return {
        "e": {"action": {"functionName": action_name}},
        **inputs,
    }


class CoffeeMachineHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handlers = {
            directory.name: load_handler(directory.name)
            for directory in COFFEE_CODE_ROOT.iterdir()
            if directory.is_dir()
        }

    def test_all_actions_return_expected_command_and_reason(self) -> None:
        cases = [
            (
                "set-heater",
                "disableHeater",
                {"measuredTemperature": 98.0, "allowedTemperature": 96.0},
                {"command": "OFF", "reason": "boiler_over_temperature"},
            ),
            (
                "set-heater",
                "enableHeater",
                {"measuredTemperature": 82.0, "requiredTemperature": 88.0},
                {"command": "ON", "reason": "group_head_warmup"},
            ),
            (
                "stop-pump",
                "stopPumpForLowWater",
                {"measuredLevel": 8.0, "minimumLevel": 10.0},
                {"command": "STOP", "reason": "low_water"},
            ),
            (
                "stop-pump",
                "stopPumpForHighPressure",
                {"measuredPressure": 11.0, "maximumPressure": 10.0},
                {"command": "STOP", "reason": "high_brew_pressure"},
            ),
            (
                "stop-pump",
                "stopPumpForFullTray",
                {"measuredLevel": 90.0, "maximumLevel": 85.0},
                {"command": "STOP", "reason": "drip_tray_full"},
            ),
            (
                "close-brew-valve",
                "closeValveAtTargetVolume",
                {"measuredVolume": 37.0, "targetVolume": 36.0, "currentFlowRate": 2.0},
                {"command": "CLOSE", "reason": "target_volume_reached"},
            ),
            (
                "close-brew-valve",
                "closeValveForHighPressure",
                {"measuredPressure": 11.0, "maximumPressure": 10.0},
                {"command": "CLOSE", "reason": "high_brew_pressure"},
            ),
            (
                "close-brew-valve",
                "closeValveForFullTray",
                {"measuredLevel": 90.0, "maximumLevel": 85.0},
                {"command": "CLOSE", "reason": "drip_tray_full"},
            ),
            (
                "close-brew-valve",
                "closeValveWithoutCup",
                {"presenceState": 0, "requiredState": 1},
                {"command": "CLOSE", "reason": "cup_missing"},
            ),
            (
                "stop-grinder",
                "stopGrinderForLowBeans",
                {"measuredLevel": 3.0, "minimumLevel": 5.0},
                {"command": "STOP", "reason": "low_bean_level"},
            ),
            (
                "stop-grinder",
                "stopStalledGrinder",
                {"measuredSpeed": 250, "minimumSpeed": 500},
                {"command": "STOP", "reason": "grinder_stall"},
            ),
            (
                "stop-grinder",
                "stopGrinderForOpenDoor",
                {"doorState": 0, "requiredState": 1},
                {"command": "STOP", "reason": "service_door_open"},
            ),
        ]

        for directory, action_name, inputs, expected in cases:
            with self.subTest(action=action_name):
                actual = self.handlers[directory].lambda_handler(
                    event_for(action_name, **inputs),
                    None,
                )
                self.assertEqual(actual, expected)

    def test_handlers_reject_unknown_actions(self) -> None:
        for directory, handler in self.handlers.items():
            with self.subTest(directory=directory):
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    handler.lambda_handler(event_for("unknownAction"), None)

    def test_handlers_reject_missing_or_non_finite_inputs(self) -> None:
        handler = self.handlers["set-heater"]

        with self.assertRaisesRegex(ValueError, "allowedTemperature must be a number"):
            handler.lambda_handler(
                event_for("disableHeater", measuredTemperature=98.0),
                None,
            )

        with self.assertRaisesRegex(ValueError, "measuredTemperature must be finite"):
            handler.lambda_handler(
                event_for(
                    "disableHeater",
                    measuredTemperature=float("nan"),
                    allowedTemperature=96.0,
                ),
                None,
            )

    def test_every_sysml_code_path_has_a_lambda_entrypoint(self) -> None:
        source = COFFEE_MODEL.read_text(encoding="utf-8")
        configured_directories = set(
            re.findall(r'/pipeline/code/coffee-machine/([^";]+)', source)
        )

        self.assertEqual(
            configured_directories,
            {"set-heater", "stop-pump", "close-brew-valve", "stop-grinder"},
        )
        for directory in configured_directories:
            self.assertTrue(
                (COFFEE_CODE_ROOT / directory / "lambda_function.py").is_file()
            )

    def test_sysml_feedback_uses_handler_results(self) -> None:
        source = COFFEE_MODEL.read_text(encoding="utf-8")

        self.assertNotIn("customPayload", source)
        self.assertEqual(source.count("reason :>> outputParameters"), 12)


if __name__ == "__main__":
    unittest.main()
