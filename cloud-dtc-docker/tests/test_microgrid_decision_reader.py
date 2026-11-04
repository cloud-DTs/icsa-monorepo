import importlib.util
import io
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch


STRATEGY_DIR = (
    Path(__file__).resolve().parents[1]
    / "demo-code/microgrid/federation/fedBatteryToChargerDecision"
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BoundedHotReader:
    """Model the deployed reader's 500-record cap with 200-record pages."""

    def __init__(self, records):
        self.records = records
        self.request = None

    def invoke(self, **kwargs):
        self.request = json.loads(kwargs["Payload"])
        descending = self.request.get("orderByTime") == "DESCENDING"
        records = sorted(self.records, key=lambda r: r["time"], reverse=descending)[:600]
        values = []
        for name in self.request["selectedProperties"]:
            value_type = self.request["properties"][name]["definition"]["dataType"]["type"]
            history = [
                {"time": r["time"], "value": {value_type.lower() + "Value": r[name]}}
                for r in records if name in r
            ]
            maximum = self.request.get("maxResults")
            if maximum:
                history = history[:maximum]
            values.append({"entityPropertyReference": {"propertyName": name}, "values": history})
        return {"Payload": io.BytesIO(json.dumps({"propertyValues": values}).encode())}


class MicrogridDecisionReaderTests(unittest.TestCase):
    def setUp(self):
        logic = load_module("decision_logic", STRATEGY_DIR / "decision_logic.py")
        boto3_stub = types.SimpleNamespace(client=lambda *args, **kwargs: None)
        with patch.dict("sys.modules", {"boto3": boto3_stub, "decision_logic": logic}):
            self.handler = load_module("microgrid_handler", STRATEGY_DIR / "lambda_function.py")
        self.logic = logic

    def pull(self, records):
        self.handler.lambda_client = BoundedHotReader(records)
        timestamps = {}
        values = self.handler._pull(
            "Battery.storage", "reader", "workspace", "entity", "storage",
            {"charge": "DOUBLE", "isPlugged": "STRING"}, timestamps=timestamps,
        )
        return values, timestamps

    def test_new_charge_is_visible_after_more_than_one_scan_window(self):
        records = [
            {"time": f"2026-09-17T06:{minute:02d}:{second:02d}.000Z", "charge": 0.0}
            for minute in range(12) for second in range(60)
        ]
        records += [
            {"time": "2026-09-17T07:18:26.306Z", "isPlugged": "true"},
            {"time": "2026-09-17T07:18:32.143Z", "charge": 50.0},
        ]
        values, timestamps = self.pull(records)
        self.assertEqual(values, {"charge": 50.0, "isPlugged": "true"})
        self.assertEqual(timestamps["charge"], "2026-09-17T07:18:32.143Z")
        ev, battery_charge = self.logic.calculate_power_split(
            70, 0, 0, 22, 10, 10, values["isPlugged"] == "true", 0, values["charge"],
        )
        self.assertEqual(ev, 10.0)
        self.assertEqual(
            self.logic.net_battery_power(70, ev, battery_charge, 10, values["charge"]), -10.0,
        )

    def test_latest_values_can_come_from_different_messages(self):
        values, timestamps = self.pull([
            {"time": "2026-09-17T07:10:00.000Z", "charge": 50.0, "isPlugged": "true"},
            {"time": "2026-09-17T07:11:00.000Z", "charge": 49.0},
            {"time": "2026-09-17T07:12:00.000Z", "isPlugged": "false"},
        ])
        self.assertEqual(values, {"charge": 49.0, "isPlugged": "false"})
        self.assertEqual(timestamps["charge"], "2026-09-17T07:11:00.000Z")
        self.assertEqual(timestamps["isPlugged"], "2026-09-17T07:12:00.000Z")


if __name__ == "__main__":
    unittest.main()
