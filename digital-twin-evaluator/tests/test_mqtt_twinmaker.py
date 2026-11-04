from concurrent.futures import Future
import json
from unittest.mock import patch

import pytest

from digital_twin_evaluation import cli
from digital_twin_evaluation.contracts import BackendError, Reading
from digital_twin_evaluation.deployment import load_deployment
from digital_twin_evaluation.evaluations.mqtt_twinmaker import MqttTwinMakerEvaluation
from test_roundtrip import FakeClock


class Publisher:
    def __init__(self, clock):
        self.clock, self.writes = clock, []
        self.closed = False
        self.pending_ack = False
        self.publish_error = None
        self.interrupt = False

    def connect(self, on_disconnect):
        self.on_disconnect = on_disconnect
        self.clock.now += 5  # Setup is excluded from each sample.

    def publish(self, topic, payload):
        self.writes.append((topic, payload))
        self.clock.now += 0.005
        future = Future()
        if self.publish_error:
            future.set_exception(BackendError(self.publish_error))
        elif not self.pending_ack:
            future.set_result({})
        if self.interrupt:
            self.on_disconnect(BackendError("lost connection"))
        return future

    def close(self):
        self.closed = True


class Reader:
    def __init__(self, publisher):
        self.publisher, self.clock = publisher, publisher.clock
        self.calls, self.replies = [], []
        self.read_seconds = 0.03

    def read_pages(self, target, prop, data_type, timestamp):
        yield self.read(target, prop, data_type, timestamp)

    def read(self, target, prop, data_type, timestamp):
        self.calls.append((target, prop, data_type, timestamp))
        self.clock.now += self.read_seconds
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            if callable(reply):
                return reply(timestamp)
            if reply is not None:
                return reply
        return [Reading(timestamp, self.publisher.writes[-1][1][prop])]


def prepare(deployment_dir, **overrides):
    return MqttTwinMakerEvaluation().prepare(load_deployment(deployment_dir), {
        "target": "MicroGrid.pv.pV1", "property": "output", "value_range": [1.0, 2.0],
        "samples": 1, "warmup": 0, "timeout_seconds": 1,
        "poll_interval_seconds": 0.05, **overrides,
    })


def test_timer_spans_mqtt_publish_until_native_twinmaker_read(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)
    result = prepare(deployment_dir).run(client=publisher, reader=reader, clock=clock)
    record = result.measurements[0]
    assert result.successful
    assert publisher.writes[0][0] == "MGridICSA/iot-data"
    assert publisher.writes[0][1]["iotDeviceId"] == "pv-sensor"
    assert record["roundtrip_ms"] == pytest.approx(35)
    assert record["write_ms"] == pytest.approx(5)
    assert record["read_ms"] == pytest.approx(30)
    assert record["publish_ack_ms"] == pytest.approx(5)
    assert record["response_timestamp"] == record["timestamp"]
    assert record["response_value"] == record["value"]
    assert publisher.closed


def test_puback_alone_does_not_prove_twinmaker_visibility(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)
    reader.replies = [[]] * 10
    result = prepare(deployment_dir, timeout_seconds=0.15).run(client=publisher, reader=reader, clock=clock)
    assert result.measurements[0]["status"] == "timeout"
    assert result.summary["successful_samples"] == 0
    assert result.summary["latencies_ms"]["roundtrip"]["max"] is None


def test_old_timestamp_and_wrong_value_require_another_query(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)
    reader.replies = [
        lambda timestamp: [Reading("2026-10-21T17:00:00Z", publisher.writes[-1][1]["output"])],
        [Reading("2026-10-22T17:00:00Z", 99.0)], [],
    ]
    result = prepare(deployment_dir).run(client=publisher, reader=reader, clock=clock)
    assert result.successful
    assert result.measurements[0]["read_attempts"] == 4
    assert len(clock.sleeps) == 3


def test_boolean_is_not_accepted_as_a_double(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)
    reader.replies = [[Reading("2026-10-22T17:00:00.000Z", True)]]
    with patch("digital_twin_evaluation.evaluations.mqtt_twinmaker.secrets.randbits", return_value=0):
        result = prepare(deployment_dir).run(client=publisher, reader=reader, clock=clock)
    assert result.measurements[0]["value"] == 1.0
    assert result.measurements[0]["read_attempts"] == 2


def test_read_after_deadline_is_not_success(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)
    reader.read_seconds = 2
    result = prepare(deployment_dir, timeout_seconds=0.1).run(client=publisher, reader=reader, clock=clock)
    assert result.measurements[0]["status"] == "timeout"


@pytest.mark.parametrize("phase", ["publish", "read", "connection"])
def test_failures_are_preserved_and_connection_loss_stops_later_publishes(deployment_dir, phase):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)
    if phase == "publish":
        publisher.publish_error = "denied"
    elif phase == "read":
        reader.replies = [BackendError("denied")]
    else:
        publisher.interrupt = True
    result = prepare(deployment_dir, samples=2 if phase == "connection" else 1).run(client=publisher, reader=reader, clock=clock)
    assert result.measurements[0]["status"] == {"publish": "write_error", "read": "read_error", "connection": "connection_error"}[phase]
    if phase == "connection":
        assert len(publisher.writes) == 1
        assert all(row["status"] == "connection_error" for row in result.measurements)
    assert publisher.closed


def test_visibility_can_be_confirmed_before_puback_is_observed(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    publisher.pending_ack = True
    result = prepare(deployment_dir).run(client=publisher, reader=Reader(publisher), clock=clock)
    assert result.successful
    assert result.measurements[0]["publish_ack_ms"] is None


def test_synchronous_publish_error_preserves_elapsed_time_and_closes_client(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)

    def fail_publish(*args):
        clock.now += 0.02
        raise BackendError("publish failed")

    publisher.publish = fail_publish
    result = prepare(deployment_dir).run(client=publisher, reader=reader, clock=clock)
    assert result.measurements[0]["status"] == "write_error"
    assert result.measurements[0]["write_ms"] == pytest.approx(20)
    assert reader.calls == [] and publisher.closed


def test_disconnect_during_a_read_cannot_turn_into_success(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)

    def interrupt(timestamp):
        publisher.on_disconnect(BackendError("lost connection"))
        return [Reading(timestamp, publisher.writes[-1][1]["output"])]

    reader.replies = [interrupt]
    result = prepare(deployment_dir).run(client=publisher, reader=reader, clock=clock)
    assert result.measurements[0]["status"] == "connection_error"


def test_all_values_and_timestamps_are_unique_and_warmup_is_excluded(deployment_dir):
    clock = FakeClock()
    publisher = Publisher(clock)
    result = prepare(deployment_dir, warmup=2, samples=4).run(client=publisher, reader=Reader(publisher), clock=clock)
    payloads = [payload for _, payload in publisher.writes]
    assert len({payload["output"] for payload in payloads}) == 6
    assert len({payload["time"] for payload in payloads}) == 6
    assert result.summary["measured_samples"] == 4
    assert result.summary["warmup_samples"] == 2
    assert result.summary["latencies_ms"]["roundtrip"]["p50"] == pytest.approx(35)


@pytest.mark.parametrize("overrides", [
    {"concurrency": 2}, {"value_range": [1, 1]}, {"value_range": [False, 2]},
    {"value_range": [1, float("inf")]}, {"property": "missing"}, {"samples": 0},
    {"timeout_seconds": 0}, {"poll_interval_seconds": 0}, {"request_timeout_seconds": True},
    {"setup_timeout_seconds": -1}, {"endpoint": "https://example.com"}, {"feedback_action": "irrelevant"},
])
def test_invalid_settings_fail_without_aws_calls(deployment_dir, overrides):
    with patch("boto3.Session") as session, pytest.raises(ValueError):
        prepare(deployment_dir, **overrides)
    session.assert_not_called()


def test_cli_plan_is_offline_and_requires_no_feedback_config(deployment_dir, tmp_path, capsys):
    config = tmp_path / "twinmaker.json"
    config.write_text(json.dumps({"schema_version": 1, "evaluation": "mqtt-twinmaker", "parameters": {
        "target": "MicroGrid.pv.pV1", "property": "output", "value_range": [1, 2],
    }}), encoding="utf-8")
    with patch("boto3.Session") as session:
        assert cli.main(["plan", "mqtt-twinmaker", "--deployment", str(deployment_dir), "--config", str(config)]) == 0
    session.assert_not_called()
    document = json.loads(capsys.readouterr().out)
    assert document["evaluation"] == "mqtt-twinmaker"
    assert document["read_api"] == "GetPropertyValueHistory"
    assert document["concurrency"] == 1


def test_cli_run_writes_the_new_evaluation_report(deployment_dir, tmp_path):
    clock = FakeClock()
    publisher = Publisher(clock)
    reader = Reader(publisher)
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"schema_version": 1, "evaluation": "mqtt-twinmaker", "parameters": {
        "target": "MicroGrid.pv.pV1", "property": "output", "value_range": [1, 2], "samples": 2, "warmup": 1,
    }}), encoding="utf-8")
    with (patch("digital_twin_evaluation.evaluations.mqtt_twinmaker.SystemClock", return_value=clock),
          patch("digital_twin_evaluation.mqtt.AwsMqttClient", return_value=publisher),
          patch("digital_twin_evaluation.aws_twinmaker.AwsTwinMakerReader", return_value=reader)):
        assert cli.main(["run", "mqtt-twinmaker", "--deployment", str(deployment_dir),
                         "--config", str(settings), "--output", str(tmp_path / "results")]) == 0
    summary_path = next((tmp_path / "results/MGridICSA").glob("*/summary.json"))
    document = json.loads(summary_path.read_text(encoding="utf-8"))
    assert document["evaluation"] == "mqtt-twinmaker"
    assert document["summary"]["successful_samples"] == 2
    assert document["summary"]["warmup_samples"] == 1
    assert "response_timestamp" in (summary_path.parent / "measurements.csv").read_text()
