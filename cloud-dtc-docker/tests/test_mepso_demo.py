import importlib.util
import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "pipeline" / "digital-twin-profile-sysml-v2" / "input"
FED_CONFIG = (
    REPO_ROOT / "pipeline" / "fed-sysml" / "input" / "fedtwin.mepso.example.json"
)


def load_decision_logic():
    path = (
        REPO_ROOT
        / "demo-code"
        / "meps-demo"
        / "aggregator-decision"
        / "decision_logic.py"
    )
    spec = importlib.util.spec_from_file_location("mepso_decision_logic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_dispatch_lambda():
    path = (
        REPO_ROOT
        / "demo-code"
        / "meps-demo"
        / "dispatch-to-community"
        / "lambda_function.py.template"
    )
    source = path.read_text(encoding="utf-8")
    for placeholder in (
        "__EC1_BATTERY_DEVICE_ID__",
        "__EC1_DSR_DEVICE_ID__",
        "__EC2_BATTERY_DEVICE_ID__",
        "__EC2_DSR_DEVICE_ID__",
        "__DSO_TS1_DEVICE_ID__",
        "__DSO_TS2_DEVICE_ID__",
    ):
        source = source.replace(placeholder, placeholder.removeprefix("__").removesuffix("__"))
    namespace = {"__name__": "mepso_dispatch_lambda"}
    exec(compile(source, path, "exec"), namespace)
    return namespace


class MEPSODecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logic = load_decision_logic()

    def test_baseline_keeps_every_power_value_at_zero(self):
        result = self.logic.calculate_dispatch(
            {
                "requestedPower": 0,
                "serviceDirection": "NONE",
                "ts1VoltageStatus": "NORMAL",
            }
        )
        self.assertEqual(result["decisionMode"], "MONITORING")
        self.assertEqual(result["ts1ExchangePower"], 0)
        self.assertEqual(result["ts2ExchangePower"], 0)

    def test_high_voltage_absorbs_six_mw_behind_ts1(self):
        result = self.logic.calculate_dispatch(
            {
                "requestedPower": 0,
                "ts1VoltageStatus": "HIGH_VOLTAGE",
                "ts1ExchangeLimit": 10,
            }
        )
        self.assertEqual(result["ec1BatteryPower"], 4)
        self.assertEqual(result["ec1DSRPower"], 2)
        self.assertEqual(result["ts1ExchangePower"], 6)
        self.assertEqual(result["ts2ExchangePower"], 0)

    def test_upward_service_delivers_eight_plus_four_mw(self):
        result = self.logic.calculate_dispatch(
            {
                "requestedPower": 12,
                "serviceDirection": "UPWARD",
                "ts1ExchangeLimit": 10,
                "ts2ExchangeLimit": 10,
            }
        )
        self.assertEqual(result["ec1BatteryPower"], -5)
        self.assertEqual(result["ec1DSRPower"], -3)
        self.assertEqual(result["ec2BatteryPower"], -3)
        self.assertEqual(result["ec2DSRPower"], -1)
        self.assertEqual(result["deliveredPower"], 12)
        self.assertEqual(
            (result["ts1ExchangePower"], result["ts2ExchangePower"]), (-8, -4)
        )

    def test_downward_service_uses_pv_and_imports_five_mw_per_ts(self):
        result = self.logic.calculate_dispatch(
            {
                "requestedPower": 10,
                "serviceDirection": "DOWNWARD",
                "ts1ExchangeLimit": 10,
                "ts2ExchangeLimit": 10,
                "ec1PVPower": 3,
                "ec2PVPower": 2,
            }
        )
        self.assertEqual(result["ec1BatteryPower"], 8)
        self.assertEqual(result["ec2BatteryPower"], 7)
        self.assertEqual(result["deliveredPower"], 10)
        self.assertEqual(
            (result["ts1ExchangePower"], result["ts2ExchangePower"]), (5, 5)
        )


class MEPSODirectTelemetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dispatch = load_dispatch_lambda()

    def test_ec1_battery_decision_is_written_as_battery_power(self):
        response = self.dispatch["lambda_handler"](
            {"decisionEC1BatteryUpdate": {"ec1BatteryPower": 4.0}}, None
        )
        body = json.loads(response["body"])
        self.assertEqual(body["iotDeviceId"], "EC1_BATTERY_DEVICE_ID")
        self.assertEqual(body["batteryPower"], 4.0)
        self.assertNotIn("batterySetpoint", body)

    def test_ec1_dsr_decision_is_written_as_dsr_power(self):
        response = self.dispatch["lambda_handler"](
            {"decisionEC1DSRUpdate": {"ec1DSRPower": 2.0}}, None
        )
        body = json.loads(response["body"])
        self.assertEqual(body["iotDeviceId"], "EC1_DSR_DEVICE_ID")
        self.assertEqual(body["dsrPower"], 2.0)
        self.assertNotIn("dsrSetpoint", body)

    def test_ec2_decisions_are_written_to_their_telemetry_devices(self):
        cases = (
            ("ec2BatteryPower", -3.0, "EC2_BATTERY_DEVICE_ID", "batteryPower"),
            ("ec2DSRPower", -1.0, "EC2_DSR_DEVICE_ID", "dsrPower"),
        )
        for source_name, value, device_id, target_name in cases:
            with self.subTest(source_name=source_name):
                response = self.dispatch["lambda_handler"](
                    {source_name: value}, None
                )
                body = json.loads(response["body"])
                self.assertEqual(body["iotDeviceId"], device_id)
                self.assertEqual(body[target_name], value)

    def test_exchange_decisions_are_written_to_dso_telemetry_devices(self):
        cases = (
            ("ts1ExchangePower", -8.0, "DSO_TS1_DEVICE_ID"),
            ("ts2ExchangePower", -4.0, "DSO_TS2_DEVICE_ID"),
        )
        for source_name, value, device_id in cases:
            with self.subTest(source_name=source_name):
                response = self.dispatch["lambda_handler"](
                    {source_name: value}, None
                )
                body = json.loads(response["body"])
                self.assertEqual(body["iotDeviceId"], device_id)
                self.assertEqual(body["exchangePower"], value)


class MEPSOConfigurationTests(unittest.TestCase):
    def test_decision_version_uses_timestamp_safe_supported_type(self):
        model = (MODEL_DIR / "dtcAggreg.sysml").read_text(encoding="utf-8")

        self.assertRegex(
            model,
            r"#measureAttribute\s+decisionVersion\s*\{\s*"
            r":>>\s+dataType\s+default\s+AttributeDataType::DOUBLE;",
        )

    def test_federation_uses_bounded_aggregator_strategy_inputs(self):
        config = json.loads(FED_CONFIG.read_text(encoding="utf-8"))
        strategies = {
            strategy["name"]: strategy["strategies"]
            for federation in config["fedTwins"]
            for strategy in federation["newStrategies"]
        }

        self.assertEqual(
            strategies["MEPSOPortfolioDecision"],
            [
                "dtcAggreg.aggregatorTSOUpdate",
                "dtcAggreg.aggregatorDSOTS1Update",
                "dtcAggreg.aggregatorDSOTS2Update",
                "dtcAggreg.aggregatorEC1PVUpdate",
                "dtcAggreg.aggregatorEC2PVUpdate",
            ],
        )
        self.assertEqual(
            strategies["MEPSOEC1BatteryDispatch"],
            ["dtcAggreg.decisionEC1BatteryUpdate"],
        )
        self.assertEqual(
            strategies["MEPSOEC1DSRDispatch"],
            ["dtcAggreg.decisionEC1DSRUpdate"],
        )
        self.assertEqual(
            strategies["MEPSOEC2BatteryDispatch"],
            ["dtcAggreg.decisionEC2BatteryUpdate"],
        )
        self.assertEqual(
            strategies["MEPSOEC2DSRDispatch"],
            ["dtcAggreg.decisionEC2DSRUpdate"],
        )
        self.assertEqual(
            strategies["MEPSOTS1ExchangeDispatch"],
            ["dtcAggreg.decisionTS1ExchangeUpdate"],
        )
        self.assertEqual(
            strategies["MEPSOTS2ExchangeDispatch"],
            ["dtcAggreg.decisionTS2ExchangeUpdate"],
        )

    def test_ec_models_receive_decisions_as_telemetry_without_dispatch_components(self):
        for twin in ("dtcEC1", "dtcEC2"):
            model = (MODEL_DIR / f"{twin}.sysml").read_text(encoding="utf-8")
            self.assertNotIn("Dispatch_Component", model)
            self.assertNotIn("batterySetpoint", model)
            self.assertNotIn("dsrSetpoint", model)

    def test_every_federation_strategy_reference_exists_in_a_model(self):
        config = json.loads(FED_CONFIG.read_text(encoding="utf-8"))
        models = {
            path.stem: path.read_text(encoding="utf-8")
            for path in MODEL_DIR.glob("dtc*.sysml")
        }
        for federation in config["fedTwins"]:
            for strategy in federation["newStrategies"]:
                for reference in strategy["strategies"]:
                    twin, action = reference.split(".")
                    self.assertIn(twin, models)
                    self.assertRegex(
                        models[twin], rf"#strategyAction\s+{re.escape(action)}\b"
                    )

    def test_every_model_lambda_path_exists_on_host(self):
        for name in ("dtcTSO", "dtcDSO", "dtcAggreg", "dtcEC1", "dtcEC2"):
            text = (MODEL_DIR / f"{name}.sysml").read_text(encoding="utf-8")
            for container_path in re.findall(r'pathToCode\s*=\s*"([^"]+)"', text):
                relative = container_path.removeprefix("/pipeline/code/")
                self.assertTrue(
                    (
                        REPO_ROOT / "demo-code" / relative / "lambda_function.py"
                    ).is_file()
                )

    def test_federation_lambda_templates_exist(self):
        config = json.loads(FED_CONFIG.read_text(encoding="utf-8"))
        for federation in config["fedTwins"]:
            for strategy in federation["newStrategies"]:
                relative = strategy["pathToCode"].removeprefix("/pipeline/code/")
                directory = REPO_ROOT / "demo-code" / relative
                self.assertTrue(
                    (directory / "lambda_function.py").is_file()
                    or (directory / "lambda_function.py.template").is_file()
                )


if __name__ == "__main__":
    unittest.main()
