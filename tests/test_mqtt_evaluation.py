import json
import math
from concurrent.futures import Future
from unittest.mock import patch

import pytest

from digital_twin_evaluation import cli
from digital_twin_evaluation.contracts import BackendError, SystemClock
from digital_twin_evaluation.deployment import load_deployment
from digital_twin_evaluation.evaluations.mqtt import MqttEvaluation
from test_roundtrip import FakeClock


@pytest.fixture
def mqtt_deployment(deployment_dir):
    configs = deployment_dir / "output/.digital-twin-manager-state/configs"
    events = [{
        "condition": "battery-entity.p16.power > battery-entity.constants.threshold",
        "action": {
            "type": "lambda", "functionName": "balance1",
            "inputParameters": [{"name": "batteryPower", "id": "battery-entity.p16.power"}],
            "feedback": {"type": "mqtt", "iotDeviceId": "controller-device", "payload": "action-result"},
        },
    }]
    (configs / "config_events.json").write_text(json.dumps(events))
    return deployment_dir


def options(**overrides):
    return {
        "target": "MicroGrid.battery.p16", "property": "power",
        "value_range": [1.0, 2.0], "feedback_action": "balance1",
        "response_value_path": ["inputs", "batteryPower"],
        "response_match": {"action": "balance1"},
        "samples": 1, "warmup": 0, "timeout_seconds": 0.02,
        **overrides,
    }


def prepare(path, **overrides):
    return MqttEvaluation().prepare(load_deployment(path), options(**overrides))


class ProcessingClient:
    def __init__(self, clock=None, behavior=None):
        self.clock = clock
        self.behavior = behavior
        self.writes = []
        self.closed = False
        self.start_error = None

    def start(self, topic, on_message, on_disconnect):
        self.topic, self.on_message, self.on_disconnect = topic, on_message, on_disconnect
        if self.clock:
            self.clock.now += 5  # Connection setup is outside sample latency.
        if self.start_error:
            raise self.start_error

    def emit(self, value, *, topic=None, retain=False, action="balance1"):
        payload = {"action": action, "inputs": {"batteryPower": value}}
        self.on_message(topic or self.topic, json.dumps(payload).encode(), retain)

    def publish(self, topic, payload):
        self.writes.append((topic, payload))
        future = Future()
        if self.clock:
            self.clock.now += 0.005
        if self.behavior:
            self.behavior(self, payload, future)
        else:
            if self.clock:
                self.clock.now += 0.010
            self.emit(payload["power"])
            future.set_result({"packet_id": 1})
        return future

    def close(self):
        self.closed = True


def test_timer_ends_at_the_matching_mqtt_callback_not_publish_return(mqtt_deployment):
    clock = FakeClock()
    def behavior(client, payload, future):
        clock.now += 0.010
        client.emit(payload["power"])
        clock.now += 2  # Caller resumes well after both receipt and deadline.
        future.set_result({})
    client = ProcessingClient(clock, behavior)
    result = prepare(mqtt_deployment).run(client=client, clock=clock)
    record = result.measurements[0]
    assert result.successful
    assert record["roundtrip_ms"] == pytest.approx(15)
    assert record["response_value"] == record["value"]
    assert client.writes[0][0] == "MGridICSA/iot-data"
    assert client.topic == "MGridICSA-controller-device"
    assert client.closed


def test_fast_reply_is_not_lost_and_puback_is_not_required_to_finish(mqtt_deployment):
    client = ProcessingClient(behavior=lambda c, p, f: c.emit(p["power"]))
    result = prepare(mqtt_deployment).run(client=client)
    assert result.successful
    assert result.measurements[0]["publish_ack_ms"] is None


def test_puback_alone_never_completes_a_cycle(mqtt_deployment):
    client = ProcessingClient(behavior=lambda c, p, f: f.set_result({}))
    result = prepare(mqtt_deployment, timeout_seconds=0.005).run(client=client)
    assert not result.successful
    assert result.measurements[0]["status"] == "timeout"
    assert result.summary["latencies_ms"]["roundtrip"]["p50"] is None


def test_wrong_values_actions_topics_retained_and_invalid_messages_are_ignored(mqtt_deployment):
    def behavior(client, payload, future):
        value = payload["power"]
        client.emit(value + 3)
        client.emit(value, action="another-action")
        client.emit(value, topic="MGridICSA/iot-data")
        client.emit(value, retain=True)
        client.emit(True)
        client.on_message(client.topic, b"not JSON", False)
        client.emit(value)
        future.set_result({})
    result = prepare(mqtt_deployment).run(client=ProcessingClient(behavior=behavior))
    assert result.successful
    assert result.summary["mqtt_messages"]["matched"] == 1
    assert result.summary["mqtt_messages"]["ignored"] == 5
    assert result.summary["mqtt_messages"]["invalid"] == 1


def test_late_reply_does_not_turn_timeout_into_success(mqtt_deployment):
    clock = FakeClock()
    def behavior(client, payload, future):
        clock.now += 0.1
        client.emit(payload["power"])
        future.set_result({})
    result = prepare(mqtt_deployment).run(client=ProcessingClient(clock, behavior), clock=clock)
    assert result.measurements[0]["status"] == "timeout"
    assert result.summary["mqtt_messages"]["late"] == 1


def test_each_cycle_has_a_unique_echo_value_and_timestamp_including_warmup(mqtt_deployment):
    clock = FakeClock()
    client = ProcessingClient(clock)
    result = prepare(mqtt_deployment, samples=4, warmup=2).run(client=client, clock=clock)
    payloads = [payload for _, payload in client.writes]
    assert len({payload["power"] for payload in payloads}) == 6
    assert len({payload["time"] for payload in payloads}) == 6
    assert all(1 <= payload["power"] <= 2 for payload in payloads)
    assert result.summary["measured_samples"] == 4
    assert result.summary["warmup_samples"] == 2
    assert result.summary["latencies_ms"]["roundtrip"]["p50"] == pytest.approx(15)


def test_previous_cycle_reply_cannot_finish_the_next_cycle(mqtt_deployment):
    previous = []
    def behavior(client, payload, future):
        if previous:
            client.emit(previous[-1])
        client.emit(payload["power"])
        client.emit(payload["power"])
        previous.append(payload["power"])
        future.set_result({})
    result = prepare(mqtt_deployment, samples=3).run(client=ProcessingClient(behavior=behavior))
    assert result.summary["successful_samples"] == 3
    assert result.summary["mqtt_messages"]["duplicate"] == 5


def test_publish_error_is_reported(mqtt_deployment):
    def behavior(client, payload, future):
        future.set_exception(RuntimeError("publish failed"))
    result = prepare(mqtt_deployment).run(client=ProcessingClient(behavior=behavior))
    assert result.measurements[0]["status"] == "write_error"
    assert "publish failed" in result.measurements[0]["error"]


def test_connection_loss_fails_pending_and_remaining_samples_without_republishing(mqtt_deployment):
    def behavior(client, payload, future):
        client.on_disconnect(BackendError("connection lost"))
        future.set_result({})
    client = ProcessingClient(behavior=behavior)
    result = prepare(mqtt_deployment, samples=3).run(client=client)
    assert len(client.writes) == 1
    assert [r["status"] for r in result.measurements] == ["connection_error"] * 3
    assert client.closed


def test_startup_failure_always_closes_the_client(mqtt_deployment):
    client = ProcessingClient()
    client.start_error = BackendError("subscription rejected")
    with pytest.raises(BackendError, match="subscription"):
        prepare(mqtt_deployment).run(client=client)
    assert client.closed


def test_plan_resolves_only_applied_feedback_without_aws(mqtt_deployment, tmp_path, capsys):
    path = tmp_path / "mqtt.json"
    path.write_text(json.dumps({"schema_version": 1, "evaluation": "mqtt", "parameters": options()}))
    with patch("boto3.Session", side_effect=AssertionError("Offline plan used AWS")):
        assert cli.main(["plan", "mqtt", "--deployment", str(mqtt_deployment), "--config", str(path)]) == 0
    description = json.loads(capsys.readouterr().out)
    assert description["response_topic"] == "MGridICSA-controller-device"
    assert description["correlation"] == "unique_sent_value"
    assert len(description["source"]["feedback_fingerprint"]) == 64


def test_explicit_reply_topic_supports_other_existing_processing_paths(deployment_dir):
    params = options(response_topic="other/feedback")
    params.pop("feedback_action")
    plan = MqttEvaluation().prepare(load_deployment(deployment_dir), params)
    assert plan.describe()["response_topic"] == "other/feedback"


def test_missing_feedback_is_rejected_instead_of_using_the_input_topic(deployment_dir):
    with pytest.raises(ValueError, match="feedback|config_events"):
        prepare(deployment_dir)


@pytest.mark.parametrize("overrides", [
    {"concurrency": 2}, {"concurrency": True}, {"samples": 0}, {"warmup": -1},
    {"value_range": [1, 1]}, {"value_range": [2, 1]}, {"value_range": [True, 2]},
    {"value_range": [1, math.inf]}, {"value_range": [1, 2, 3]},
    {"response_value_path": []}, {"response_value_path": "inputs.batteryPower"},
    {"response_match": []}, {"response_topic": "MGridICSA/iot-data"},
    {"response_topic": "reply/#"}, {"endpoint": "https://host/mqtt"},
    {"timeout_seconds": 0}, {"typo": 1},
])
def test_invalid_configs_are_rejected_before_clients(mqtt_deployment, overrides):
    with pytest.raises(ValueError):
        prepare(mqtt_deployment, **overrides)


@pytest.mark.parametrize("change", [
    lambda e: e.clear(),
    lambda e: e[0]["action"]["feedback"].update(payload="constant"),
    lambda e: e[0]["action"].update(inputParameters=[]),
    lambda e: e.append(e[0]),
])
def test_unusable_applied_routes_fail_offline(mqtt_deployment, change):
    path = mqtt_deployment / "output/.digital-twin-manager-state/configs/config_events.json"
    events = json.loads(path.read_text())
    change(events)
    path.write_text(json.dumps(events))
    with pytest.raises(ValueError):
        prepare(mqtt_deployment)


def test_json_string_body_can_be_selected_without_a_jsonpath_dependency(mqtt_deployment):
    def behavior(client, payload, future):
        body = json.dumps({"inputs": {"batteryPower": payload["power"]}})
        client.on_message(client.topic, json.dumps({"body": body}).encode(), False)
        future.set_result({})
    result = prepare(mqtt_deployment, response_value_path=["body", "inputs", "batteryPower"], response_match={}).run(
        client=ProcessingClient(behavior=behavior),
    )
    assert result.successful


def test_a_missing_expected_null_field_is_not_a_match(mqtt_deployment):
    result = prepare(mqtt_deployment, response_match={"missing": None}, timeout_seconds=0.005).run(
        client=ProcessingClient(),
    )
    assert result.measurements[0]["status"] == "timeout"


def test_report_preserves_the_received_numeric_value(mqtt_deployment):
    client = ProcessingClient(behavior=lambda c, p, f: c.emit(1))
    with patch("digital_twin_evaluation.evaluations.mqtt.secrets.randbits", return_value=0):
        result = prepare(mqtt_deployment).run(client=client)
    assert result.successful
    assert type(result.measurements[0]["response_value"]) is int


def test_broker_echo_topic_is_rejected_even_for_explicit_processing_routes(deployment_dir):
    params = options(response_topic="MGridICSA/iot-data")
    params.pop("feedback_action")
    with pytest.raises(ValueError, match="echo|differ"):
        MqttEvaluation().prepare(load_deployment(deployment_dir), params)


def test_cli_mqtt_run_writes_the_common_report(mqtt_deployment, tmp_path, capsys):
    config = tmp_path / "mqtt.json"
    config.write_text(json.dumps({"schema_version": 1, "evaluation": "mqtt", "parameters": options()}))
    with patch("digital_twin_evaluation.mqtt.AwsMqttClient", return_value=ProcessingClient()):
        assert cli.main(["run", "mqtt", "--deployment", str(mqtt_deployment),
                         "--config", str(config), "--output", str(tmp_path / "results")]) == 0
    output = json.loads(capsys.readouterr().out)
    from pathlib import Path
    directory = Path(output["report_directory"])
    summary = json.loads((directory / "summary.json").read_text())
    assert summary["evaluation"] == "mqtt"
    assert summary["plan"]["correlation"] == "unique_sent_value"
    assert "response_value" in (directory / "measurements.csv").read_text()
