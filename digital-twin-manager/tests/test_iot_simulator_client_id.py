import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def simulator(monkeypatch, tmp_path):
  client = Mock()
  factory = Mock(return_value=client)
  sdk = ModuleType("AWSIoTPythonSDK")
  mqtt = ModuleType("AWSIoTPythonSDK.MQTTLib")
  mqtt.AWSIoTMQTTClient = factory
  settings = SimpleNamespace(
    project_path=lambda: str(tmp_path),
    config={"topic": "MGridICSA/iot-data", "auth_files_path": "certs", "root_ca_cert_path": "rootCA.pem", "endpoint": "example.invalid"},
  )
  monkeypatch.setitem(sys.modules, "AWSIoTPythonSDK", sdk)
  monkeypatch.setitem(sys.modules, "AWSIoTPythonSDK.MQTTLib", mqtt)
  monkeypatch.setitem(sys.modules, "globals", settings)
  path = Path(__file__).resolve().parents[1] / "iot_device_simulator/src/transmission.py"
  spec = importlib.util.spec_from_file_location("simulator_transmission", path)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module, factory, client, settings


def test_simulator_connects_as_its_thing_and_preserves_device_payload_and_credentials(simulator):
  module, factory, client, _ = simulator
  payload = {"iotDeviceId": "sensor-a", "time": "2026-10-27T00:00:00Z", "power": 12.5}
  module.send_mqtt(payload)
  factory.assert_called_once_with("MGridICSA-sensor-a")
  topic, body, qos = client.publish.call_args.args
  assert topic == "MGridICSA/iot-data" and json.loads(body) == payload and qos == 1
  credentials = client.configureCredentials.call_args.args
  assert Path(credentials[1]).parts[-3:] == ("certs", "sensor-a", "private.pem.key")
  assert Path(credentials[2]).parts[-3:] == ("certs", "sensor-a", "certificate.pem.crt")
  client.disconnect.assert_called_once()


@pytest.mark.parametrize("topic", ["custom-topic", "OtherTwin/commands", "/iot-data", "a/b/iot-data"])
def test_simulator_rejects_topics_that_cannot_identify_the_registered_thing(simulator, topic):
  module, factory, _, settings = simulator
  settings.config["topic"] = topic
  with pytest.raises(ValueError, match="topic"):
    module.send_mqtt({"iotDeviceId": "sensor-a"})
  factory.assert_not_called()
