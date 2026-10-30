from datetime import datetime, timezone

import pytest

from digital_twin_evaluation.contracts import BackendError, Reading
from digital_twin_evaluation.deployment import load_deployment
from digital_twin_evaluation.evaluations.roundtrip import RoundtripEvaluation


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def utcnow(self):
        return datetime(2026, 10, 22, 17, 0, tzinfo=timezone.utc)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeBackend:
    def __init__(self, clock, replies=None):
        self.clock = clock
        self.replies = list(replies or [])
        self.writes = []
        self.reads = []
        self.write_error = None
        self.write_seconds = 0.02
        self.read_seconds = 0.03

    def write(self, mode, payload):
        self.clock.now += self.write_seconds
        if self.write_error:
            raise BackendError(self.write_error)
        self.writes.append((mode, payload))

    def read(self, target, property_name, data_type, timestamp):
        self.clock.now += self.read_seconds
        self.reads.append((target, property_name, data_type, timestamp))
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            if reply is not None:
                return reply
        return [Reading(timestamp, self.writes[-1][1][property_name])]


def prepare(deployment_dir, **options):
    parameters = {
        "target": "MicroGrid.pv.pV1", "property": "output", "value": 12.5,
        "samples": 1, "warmup": 0, "timeout_seconds": 1,
        "poll_interval_seconds": 0.05,
        **options,
    }
    return RoundtripEvaluation().prepare(load_deployment(deployment_dir), parameters)


@pytest.mark.parametrize("mode", ["storage", "ingestion"])
def test_full_roundtrip_measures_from_send_until_verified_response(deployment_dir, mode):
    clock = FakeClock()
    backend = FakeBackend(clock)
    result = prepare(deployment_dir, mode=mode).run(backend=backend, clock=clock)
    record = result.measurements[0]
    assert result.successful is True
    assert backend.writes[0][0] == mode
    assert backend.writes[0][1]["iotDeviceId"] == "pv-sensor"
    assert record["roundtrip_ms"] == pytest.approx(50)
    assert record["write_ms"] == pytest.approx(20)
    assert record["read_ms"] == pytest.approx(30)
    assert record["read_attempts"] == 1


def test_an_old_record_with_the_same_value_does_not_finish_the_cycle(deployment_dir):
    clock = FakeClock()
    backend = FakeBackend(clock, [[Reading("old-time", 12.5)], None])
    result = prepare(deployment_dir).run(backend=backend, clock=clock)
    record = result.measurements[0]
    assert record["read_attempts"] == 2
    assert record["roundtrip_ms"] == pytest.approx(130)
    assert record["read_ms"] == pytest.approx(60)
    assert clock.sleeps == [0.05]


def test_wrong_value_at_the_correct_timestamp_requires_another_read(deployment_dir):
    clock = FakeClock()
    timestamp = "2026-10-22T17:00:00.000Z"
    backend = FakeBackend(clock, [[Reading(timestamp, 999)], None])
    result = prepare(deployment_dir).run(backend=backend, clock=clock)
    assert result.measurements[0]["read_attempts"] == 2


def test_zero_is_not_confused_with_a_boolean(deployment_dir):
    clock = FakeClock()
    timestamp = "2026-10-22T17:00:00.000Z"
    backend = FakeBackend(clock, [[Reading(timestamp, False)], None])
    result = prepare(deployment_dir, value=0.0).run(backend=backend, clock=clock)
    assert result.measurements[0]["read_attempts"] == 2


def test_visibility_timeout_is_a_failed_sample(deployment_dir):
    clock = FakeClock()
    backend = FakeBackend(clock, [[]] * 100)
    result = prepare(deployment_dir, timeout_seconds=0.15).run(backend=backend, clock=clock)
    assert result.successful is False
    assert result.measurements[0]["status"] == "timeout"
    assert result.summary["failed_samples"] == 1
    assert clock.now == pytest.approx(0.15)
    assert result.summary["latencies_ms"]["roundtrip"]["p50"] is None


def test_inflight_read_past_the_deadline_is_not_success(deployment_dir):
    clock = FakeClock()
    backend = FakeBackend(clock)
    backend.read_seconds = 2
    result = prepare(deployment_dir, timeout_seconds=0.1).run(backend=backend, clock=clock)
    assert result.measurements[0]["status"] == "timeout"


@pytest.mark.parametrize("error_phase", ["write", "read"])
def test_backend_errors_are_preserved_as_failed_measurements(deployment_dir, error_phase):
    clock = FakeClock()
    backend = FakeBackend(clock)
    if error_phase == "write":
        backend.write_error = "denied"
    else:
        backend.replies = [BackendError("denied")]
    result = prepare(deployment_dir).run(backend=backend, clock=clock)
    assert result.successful is False
    assert result.measurements[0]["status"] == f"{error_phase}_error"
    assert "denied" in result.measurements[0]["error"]


def test_warmup_records_are_retained_and_excluded_from_percentiles(deployment_dir):
    clock = FakeClock()
    backend = FakeBackend(clock, [[]] * 10)
    result = prepare(deployment_dir, warmup=1, timeout_seconds=0.15).run(backend=backend, clock=clock)
    # The warmup times out; the measured sample is also a failure until visible.
    assert len(result.measurements) == 2
    assert result.measurements[0]["phase"] == "warmup"
    assert result.measurements[1]["phase"] == "measured"
    assert result.summary["measured_samples"] == 1
    assert result.summary["warmup_samples"] == 1
    assert result.summary["warmup_failed"] == 1


def test_timestamps_are_unique_even_when_the_wall_clock_does_not_advance(deployment_dir):
    clock = FakeClock()
    backend = FakeBackend(clock)
    result = prepare(deployment_dir, samples=3).run(backend=backend, clock=clock)
    timestamps = [payload["time"] for _, payload in backend.writes]
    assert len(set(timestamps)) == 3
    assert timestamps == sorted(timestamps)
    assert result.summary["latencies_ms"]["roundtrip"]["p50"] == pytest.approx(50)


@pytest.mark.parametrize("options", [
    {"samples": 0}, {"samples": True}, {"warmup": -1},
    {"poll_interval_seconds": 0}, {"timeout_seconds": float("nan")},
    {"timeout_seconds": True}, {"mode": "unknown"},
    {"value": float("inf")}, {"value": True}, {"typo": 1},
])
def test_invalid_parameters_fail_before_any_aws_client_is_created(deployment_dir, options):
    with pytest.raises(ValueError):
        prepare(deployment_dir, **options)
