import importlib
import json
from pathlib import Path

from simulator.domain import Twin


def test_shared_type_publishes_each_device_id_and_keeps_stop_state_separate(monkeypatch):
    module = importlib.import_module("simulator.SimulationLoop")
    monkeypatch.setenv("SIMULATOR_MOCK_AWS", "true")
    loop = module.SimulationLoop("shared-demo/iot-data")
    folder = Path(__file__).resolve().parents[1] / "input" / "shared-component-type"
    twin = Twin()
    twin.read_from_json(folder / "config.json", folder / "config_iot_devices.json", folder / "config_hierarchy.json")
    rows = twin.flatten()
    attributes = {bound.iotDeviceId: attribute for _, bound, attribute in rows}
    messages = []

    class RecordingClient:
        def publish(self, *, topic, qos, payload):
            message = json.loads(payload)
            messages.append((topic, qos, message))
            loop.stop_one(attributes[message["iotDeviceId"]])
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    loop.mock_aws = False
    loop.client = RecordingClient()
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    for _, _, attribute in rows:
        loop.active_runs[attribute.id] = {"run": True, "generation": 1}

    for index, (_, bound, attribute) in enumerate(rows):
        loop._loop(attribute, bound.iotDeviceId, {"mode": "uniform", "min": 21, "max": 21}, 1)
        assert loop.is_running(attribute.id) is False
        if index == 0:
            assert loop.is_running(rows[1][2].id) is True

    assert [message["iotDeviceId"] for _, _, message in messages] == ["sensor-a", "sensor-b"]
    for topic, qos, message in messages:
        assert (topic, qos) == ("shared-demo/iot-data", 1)
        assert set(message) == {"iotDeviceId", "time", "temperature"}
        assert message["temperature"] == 21.0
        assert message["time"].endswith("Z")
