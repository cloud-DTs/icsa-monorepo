import csv
import json
from unittest.mock import patch

import pytest

from digital_twin_evaluation import cli
from digital_twin_evaluation.contracts import BackendError
from digital_twin_evaluation.deployment import load_deployment
from digital_twin_evaluation.evaluations.roundtrip import RoundtripEvaluation
from digital_twin_evaluation.reporting import write_report
from test_roundtrip import FakeBackend, FakeClock


def parameters(**overrides):
    return {
        "targets": [
            {"target": "MicroGrid.pv.pV1", "property": "output", "value": 12.5},
            {"target": "MicroGrid.battery.p16", "property": "power", "value": -2.0},
        ],
        "samples": 2, "warmup": 1,
        **overrides,
    }


def prepare(deployment_dir, **overrides):
    return RoundtripEvaluation().prepare(load_deployment(deployment_dir), parameters(**overrides))


@pytest.mark.parametrize("mode", ["storage", "ingestion"])
def test_each_device_gets_its_own_warmup_measurements_and_statistics(deployment_dir, mode):
    clock = FakeClock()
    backend = FakeBackend(clock)
    result = prepare(deployment_dir, mode=mode).run(backend=backend, clock=clock)

    assert result.successful is True
    assert [payload["iotDeviceId"] for _, payload in backend.writes] == ["pv-sensor"] * 3 + ["battery-sensor"] * 3
    assert all(sent_mode == mode for sent_mode, _ in backend.writes)
    assert [payload.get("output", payload.get("power")) for _, payload in backend.writes] == [12.5] * 3 + [-2.0] * 3
    assert result.summary["target_count"] == 2
    assert result.summary["measured_samples"] == 4
    assert result.summary["warmup_samples"] == 2
    assert result.summary["failed_samples"] == 0
    for target in result.summary["targets"]:
        assert target["measured_samples"] == 2
        assert target["warmup_samples"] == 1
        assert target["latencies_ms"]["roundtrip"]["p95"] == pytest.approx(50)
    assert [record["sequence"] for record in result.measurements] == list(range(6))
    assert {record["run_id"] for record in result.measurements} == {result.run_id}


def test_one_failed_device_does_not_skip_remaining_devices(deployment_dir):
    class FailingPV(FakeBackend):
        def write(self, mode, payload):
            if payload["iotDeviceId"] == "pv-sensor":
                raise BackendError("PV unavailable")
            super().write(mode, payload)

    clock = FakeClock()
    backend = FailingPV(clock)
    result = prepare(deployment_dir, warmup=0).run(backend=backend, clock=clock)

    assert result.successful is False
    assert result.summary["failed_samples"] == 2
    assert result.summary["successful_samples"] == 2
    assert result.summary["targets"][0]["failed_samples"] == 2
    assert result.summary["targets"][1]["successful_samples"] == 2
    assert len(backend.reads) == 2


def test_multiple_devices_share_one_backend_client(deployment_dir):
    clock = FakeClock()
    backend = FakeBackend(clock)
    with (
        patch("digital_twin_evaluation.aws.AwsTelemetryBackend", return_value=backend) as create,
        patch("digital_twin_evaluation.evaluations.roundtrip.SystemClock", return_value=clock),
    ):
        result = prepare(deployment_dir, warmup=0).run()
    assert create.call_count == 1
    assert result.summary["successful_samples"] == 4
    assert len(backend.reads) == 4


@pytest.mark.parametrize("overrides", [
    {"targets": []}, {"targets": None}, {"targets": "all"},
    {"targets": ["MicroGrid.pv.pV1"]},
    {"targets": [{"target": "MicroGrid.pv.pV1", "value": 12.5}]},
    {"targets": [{"target": "MicroGrid.pv.pV1", "property": "output", "value": 1, "typo": True}]},
    {"targets": [{"target": "MicroGrid.pv.pV1", "property": "output", "value": 1}] * 2},
    {"target": "MicroGrid.pv.pV1"}, {"property": "output"}, {"value": 12.5},
])
def test_invalid_target_lists_fail_before_aws_access(deployment_dir, overrides):
    with patch("boto3.Session", side_effect=AssertionError("invalid config accessed AWS")):
        with pytest.raises(ValueError):
            prepare(deployment_dir, **overrides)


def test_offline_plan_validates_and_resolves_every_device(deployment_dir, tmp_path, capsys):
    config = tmp_path / "multi.json"
    config.write_text(json.dumps({"schema_version": 1, "evaluation": "roundtrip", "parameters": parameters()}))
    with patch("boto3.Session", side_effect=AssertionError("offline plan accessed AWS")):
        assert cli.main(["plan", "roundtrip", "--deployment", str(deployment_dir), "--config", str(config)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert [item["device_id"] for item in plan["targets"]] == ["pv-sensor", "battery-sensor"]
    assert [item["value"] for item in plan["targets"]] == [12.5, -2.0]
    assert plan["parameters"]["samples"] == 2
    assert plan["execution"] == "sequential"


def test_unknown_later_device_stops_the_run_before_any_write(deployment_dir, tmp_path, capsys):
    options = parameters()
    options["targets"][1]["target"] = "MicroGrid.missing.sensor"
    config = tmp_path / "invalid.json"
    config.write_text(json.dumps({"schema_version": 1, "evaluation": "roundtrip", "parameters": options}))
    with patch("boto3.Session", side_effect=AssertionError("invalid target accessed AWS")):
        assert cli.main(["run", "roundtrip", "--deployment", str(deployment_dir), "--config", str(config)]) == 2
    assert "Unknown target" in capsys.readouterr().err


def test_multi_device_report_identifies_each_measurement(deployment_dir, tmp_path):
    clock = FakeClock()
    result = prepare(deployment_dir, warmup=0).run(backend=FakeBackend(clock), clock=clock)
    report = write_report(result, tmp_path / "reports")
    summary = json.loads((report / "summary.json").read_text())
    with (report / "measurements.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert summary["summary"]["target_count"] == 2
    assert len(summary["summary"]["targets"]) == 2
    assert {(row["target"], row["property"], row["device_id"]) for row in rows} == {
        ("MicroGrid.pv.pV1", "output", "pv-sensor"),
        ("MicroGrid.battery.p16", "power", "battery-sensor"),
    }
