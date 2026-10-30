from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from threading import Barrier, Event, Lock
from unittest.mock import patch

import pytest

from digital_twin_evaluation import cli
from digital_twin_evaluation.contracts import BackendError, Reading, SystemClock
from test_roundtrip import prepare as prepare_single
from test_roundtrip_targets import parameters, prepare as prepare_many


class FrozenWallClock(SystemClock):
    @staticmethod
    def utcnow():
        return datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


class ConcurrentBackend:
    def __init__(self, first_wave, fail_devices=()):
        self.lock = Lock()
        self.barrier = Barrier(first_wave)
        self.first_wave = first_wave
        self.fail_devices = set(fail_devices)
        self.active = 0
        self.peak = 0
        self.writes = []
        self.reads = []
        self.values = {}

    def write(self, mode, payload):
        key = (payload["iotDeviceId"], payload["time"])
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.writes.append((mode, dict(payload)))
            first_wave = len(self.writes) <= self.first_wave
            assert key not in self.values, "A concurrent write reused a device/timestamp key"
            self.values[key] = payload
        if first_wave:
            self.barrier.wait(timeout=5)
        if payload["iotDeviceId"] in self.fail_devices:
            with self.lock:
                self.active -= 1
            raise BackendError("device unavailable")

    def read(self, target, property_name, data_type, timestamp):
        with self.lock:
            value = self.values[(target.device_id, timestamp)][property_name]
            self.reads.append((target.device_id, timestamp))
            self.active -= 1
        return [Reading(timestamp, value)]


@pytest.mark.parametrize("many", [False, True])
@pytest.mark.parametrize("mode", ["storage", "ingestion"])
def test_roundtrips_are_parallel_and_globally_bounded(deployment_dir, many, mode):
    backend = ConcurrentBackend(first_wave=3)
    prepare = prepare_many if many else prepare_single
    result = prepare(deployment_dir, concurrency=3, samples=5, warmup=0, mode=mode).run(
        backend=backend, clock=FrozenWallClock(),
    )
    count = 10 if many else 5
    assert result.successful is True
    assert backend.peak == 3
    assert backend.active == 0
    assert len(backend.writes) == len(backend.reads) == count
    assert {sent_mode for sent_mode, _ in backend.writes} == {mode}
    assert len({(payload["iotDeviceId"], payload["time"]) for _, payload in backend.writes}) == count
    assert [record["sequence"] for record in result.measurements] == list(range(count))
    assert {record["run_id"] for record in result.measurements} == {result.run_id}
    assert result.plan["execution"] == "parallel"
    assert result.summary["measured_samples"] == count
    assert result.summary["measured_duration_ms"] > 0
    assert result.summary["successful_samples_per_second"] > 0
    if many:
        assert {payload["iotDeviceId"] for _, payload in backend.writes[:3]} == {"pv-sensor", "battery-sensor"}
        assert [target["successful_samples"] for target in result.summary["targets"]] == [5, 5]


def test_all_warmup_cycles_finish_before_any_measured_write(deployment_dir):
    class WarmupBackend(ConcurrentBackend):
        def __init__(self):
            super().__init__(first_wave=2)
            self.pv_read_started = Event()
            self.battery_read_done = Event()
            self.release_pv = Event()
            self.measured_write = Event()
            self.per_device_writes = {}

        def write(self, mode, payload):
            with self.lock:
                device = payload["iotDeviceId"]
                self.per_device_writes[device] = self.per_device_writes.get(device, 0) + 1
                if self.per_device_writes[device] > 1:
                    self.measured_write.set()
            super().write(mode, payload)

        def read(self, target, property_name, data_type, timestamp):
            if target.device_id == "pv-sensor" and not self.pv_read_started.is_set():
                self.pv_read_started.set()
                assert self.release_pv.wait(timeout=5)
            reading = super().read(target, property_name, data_type, timestamp)
            if target.device_id == "battery-sensor":
                self.battery_read_done.set()
            return reading

    backend = WarmupBackend()
    with ThreadPoolExecutor(max_workers=1) as runner:
        future = runner.submit(
            prepare_many(deployment_dir, concurrency=2, samples=3, warmup=1).run,
            backend=backend, clock=FrozenWallClock(),
        )
        try:
            assert backend.pv_read_started.wait(timeout=5)
            assert backend.battery_read_done.wait(timeout=5)
            assert not backend.measured_write.wait(timeout=0.05)
        finally:
            backend.release_pv.set()
        result = future.result(timeout=5)
    assert result.summary["warmup_samples"] == 2
    assert result.summary["measured_samples"] == 6
    assert result.summary["failed_samples"] == 0
    assert len({(payload["iotDeviceId"], payload["time"]) for _, payload in backend.writes}) == 8


def test_parallel_device_errors_are_retained_and_other_devices_continue(deployment_dir):
    backend = ConcurrentBackend(first_wave=2, fail_devices={"pv-sensor"})
    result = prepare_many(deployment_dir, concurrency=3, samples=3, warmup=1).run(
        backend=backend, clock=FrozenWallClock(),
    )
    assert result.successful is False
    assert result.summary["failed_samples"] == 3
    assert result.summary["successful_samples"] == 3
    assert result.summary["warmup_failed"] == 1
    assert result.summary["targets"][0]["statuses"] == {"write_error": 3}
    assert result.summary["targets"][1]["successful_samples"] == 3
    assert len(result.measurements) == 8


def test_large_runs_do_not_queue_every_sample_at_once(deployment_dir):
    release = Event()
    first_wave = Event()
    third_submission = Event()

    class GatedBackend(ConcurrentBackend):
        def write(self, mode, payload):
            super().write(mode, payload)
            first_wave.set()
            assert release.wait(timeout=5)

    class RecordingExecutor:
        def __init__(self, **kwargs):
            self.executor = ThreadPoolExecutor(**kwargs)
            self.submissions = 0

        def __enter__(self):
            return self

        def __exit__(self, *exception):
            self.executor.shutdown(wait=True)

        def submit(self, *args):
            self.submissions += 1
            if self.submissions > 2:
                third_submission.set()
            return self.executor.submit(*args)

    backend = GatedBackend(first_wave=2)
    with (
        patch("digital_twin_evaluation.evaluations.roundtrip_parallel.ThreadPoolExecutor", RecordingExecutor),
        ThreadPoolExecutor(max_workers=1) as runner,
    ):
        future = runner.submit(
            prepare_single(deployment_dir, concurrency=2, samples=50, warmup=0).run,
            backend=backend, clock=FrozenWallClock(),
        )
        try:
            assert first_wave.wait(timeout=5)
            assert not third_submission.wait(timeout=0.05)
        finally:
            release.set()
        result = future.result(timeout=5)
    assert result.summary["successful_samples"] == 50
    assert backend.peak == 2


@pytest.mark.parametrize("concurrency", [0, -1, True, 1.5, "10"])
def test_invalid_concurrency_is_rejected_before_aws_access(deployment_dir, concurrency):
    with patch("boto3.Session", side_effect=AssertionError("invalid config accessed AWS")):
        with pytest.raises(ValueError):
            prepare_many(deployment_dir, concurrency=concurrency)


def test_offline_plan_describes_parallel_execution(deployment_dir, tmp_path, capsys):
    path = tmp_path / "parallel.json"
    path.write_text(json.dumps({
        "schema_version": 1, "evaluation": "roundtrip", "parameters": parameters(concurrency=20),
    }))
    with patch("boto3.Session", side_effect=AssertionError("offline plan accessed AWS")):
        assert cli.main(["plan", "roundtrip", "--deployment", str(deployment_dir), "--config", str(path)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["execution"] == "parallel"
    assert plan["parameters"]["concurrency"] == 20


def test_single_worker_keeps_sequential_execution(deployment_dir):
    backend = ConcurrentBackend(first_wave=1)
    result = prepare_many(deployment_dir, concurrency=1, samples=2, warmup=0).run(backend=backend)
    assert result.successful is True
    assert backend.peak == 1
    assert result.plan["execution"] == "sequential"


def test_parallel_backend_initializes_clients_before_workers(deployment_dir):
    backend = ConcurrentBackend(first_wave=2)
    with patch("digital_twin_evaluation.aws.AwsTelemetryBackend", return_value=backend) as create:
        result = prepare_single(deployment_dir, concurrency=2, samples=3, warmup=0, mode="ingestion").run()
    assert result.successful is True
    assert create.call_count == 1
    assert create.call_args.kwargs["max_pool_connections"] >= 2
    assert create.call_args.kwargs["mode"] == "ingestion"
