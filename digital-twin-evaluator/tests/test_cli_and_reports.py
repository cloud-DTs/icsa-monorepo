import csv
import json
from unittest.mock import patch

import pytest

from digital_twin_evaluation import cli
from digital_twin_evaluation.config import load_config
from digital_twin_evaluation.evaluations import EVALUATIONS
from digital_twin_evaluation.evaluations.roundtrip import RoundtripEvaluation
from digital_twin_evaluation.deployment import load_deployment
from digital_twin_evaluation.reporting import write_report
from digital_twin_evaluation.contracts import BackendError
from test_roundtrip import FakeBackend, FakeClock


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps({
        "schema_version": 1, "evaluation": "roundtrip", "parameters": {
            "target": "MicroGrid.pv.pV1", "property": "output", "value": -2.5,
            "samples": 2, "warmup": 1,
        },
    }))
    return path


def test_offline_plan_never_creates_an_aws_session(deployment_dir, config_file, capsys):
    with patch("boto3.Session", side_effect=AssertionError("offline plan accessed AWS")):
        assert cli.main(["plan", "roundtrip", "--deployment", str(deployment_dir), "--config", str(config_file)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["parameters"]["mode"] == "storage"
    assert plan["target"]["device_id"] == "pv-sensor"


def test_reports_preserve_raw_warmup_and_measured_samples(deployment_dir, config_file, tmp_path):
    config = load_config(config_file)
    prepared = RoundtripEvaluation().prepare(load_deployment(deployment_dir), config.parameters)
    clock = FakeClock()
    result = prepared.run(backend=FakeBackend(clock), clock=clock)
    path = write_report(result, tmp_path / "reports")
    summary = json.loads((path / "summary.json").read_text())
    with (path / "measurements.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert path.parent.name == "MGridICSA"
    assert summary["schema_version"] == 1
    assert summary["successful"] is True
    assert summary["summary"]["measured_samples"] == 2
    assert len(rows) == 3
    assert rows[0]["phase"] == "warmup"
    assert all(json.loads(row["value"]) == -2.5 for row in rows)
    assert summary["plan"]["source"]["fingerprint"] == load_deployment(deployment_dir).fingerprint


def test_another_evaluation_registers_without_changing_the_cli(deployment_dir, config_file, capsys):
    raw = json.loads(config_file.read_text())
    raw["evaluation"] = "other"
    config_file.write_text(json.dumps(raw))
    class Prepared:
        def describe(self):
            return {"evaluation": "other", "works": True}
    class Other:
        def prepare(self, deployment, parameters):
            return Prepared()
    with patch.dict(EVALUATIONS, {"other": Other()}):
        assert cli.main(["plan", "other", "--deployment", str(deployment_dir), "--config", str(config_file)]) == 0
    assert json.loads(capsys.readouterr().out) == {"evaluation": "other", "works": True}


def test_cli_rejects_a_config_for_another_evaluation(deployment_dir, config_file, capsys):
    assert cli.main(["plan", "other", "--deployment", str(deployment_dir), "--config", str(config_file)]) == 2
    assert "does not match" in capsys.readouterr().err


def test_unknown_config_fields_are_rejected(config_file):
    raw = json.loads(config_file.read_text())
    raw["typo"] = True
    config_file.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        load_config(config_file)


def test_backend_startup_failure_returns_a_clear_cli_error(deployment_dir, config_file, capsys):
    with patch("digital_twin_evaluation.evaluations.roundtrip.RoundtripPlan.run", side_effect=BackendError("credentials unavailable")):
        assert cli.main(["run", "roundtrip", "--deployment", str(deployment_dir), "--config", str(config_file)]) == 2
    assert "credentials unavailable" in capsys.readouterr().err
