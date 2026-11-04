import copy
import importlib.util
import json
import os
import sys
import types
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def load_persister(monkeypatch):
    def load(debug=None):
        monkeypatch.delenv("DEBUG", raising=False)
        table = MagicMock()
        lambda_client = MagicMock()
        boto3 = types.ModuleType("boto3")
        boto3.resource = lambda *args: types.SimpleNamespace(Table=lambda name: table)
        boto3.client = lambda *args: lambda_client
        environment = {
            "DYNAMODB_TABLE_NAME": "dt-hot",
            "EVENT_CHECKER_LAMBDA_NAME": "dt-event-checker",
        }
        if debug is not None:
            environment["DEBUG"] = debug
        path = REPO_ROOT / "lambda_functions/core/persister/lambda_function.py"
        spec = importlib.util.spec_from_file_location("persister_under_test", path)
        runtime = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"boto3": boto3}), patch.dict(os.environ, environment):
            spec.loader.exec_module(runtime)
        return runtime, table, lambda_client

    return load


@pytest.fixture
def event():
    return {
        "iotDeviceId": "sensor-a",
        "time": "2026-10-21T10:00:00.000Z",
        "temperature": 21.5,
        "iot_ingested_at_ms": 1000,
    }


@pytest.mark.parametrize("debug", [None, "False", "false", "invalid"])
def test_disabled_debug_keeps_existing_write_behavior(load_persister, event, debug, capsys):
    runtime, table, lambda_client = load_persister(debug)
    original = copy.deepcopy(event)
    with patch("time.time_ns") as clock:
        runtime.lambda_handler(event, None)

    item = table.put_item.call_args.kwargs["Item"]
    assert item == {
        "iotDeviceId": "sensor-a",
        "id": event["time"],
        "temperature": Decimal("21.5"),
        "iot_ingested_at_ms": 1000,
    }
    clock.assert_not_called()
    assert event == original
    assert json.loads(lambda_client.invoke.call_args.kwargs["Payload"]) == event
    assert not any(line.startswith("{") for line in capsys.readouterr().out.splitlines())


@pytest.mark.parametrize("debug", ["True", "true", "TRUE", " true "])
def test_debug_stores_ingestion_and_write_start_and_logs_acknowledgement(
    load_persister, event, debug, capsys,
):
    runtime, table, lambda_client = load_persister(debug)
    original = copy.deepcopy(event)
    calls = []
    table.put_item.side_effect = lambda **kwargs: calls.append("put_item")

    def now():
        calls.append("clock")
        return 1_050_000_000 if len(calls) == 1 else 1_080_000_000

    with patch("time.time_ns", side_effect=now):
        runtime.lambda_handler(event, types.SimpleNamespace(aws_request_id="request-1"))

    item = table.put_item.call_args.kwargs["Item"]
    assert item["iot_ingested_at_ms"] == 1000
    assert item["db_write_started_at_ms"] == 1050
    assert item["ingestion_to_write_ms"] == 50
    assert item["id"] == event["time"]
    assert item["temperature"] == Decimal("21.5")
    assert "db_write_ack_at_ms" not in item
    assert calls == ["clock", "put_item", "clock"]
    assert event == original
    assert json.loads(lambda_client.invoke.call_args.kwargs["Payload"]) == event
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert len(records) == 1
    assert records[0]["event"] == "telemetry_persisted"
    assert records[0]["request_id"] == "request-1"
    assert records[0]["iotDeviceId"] == "sensor-a"
    assert records[0]["db_write_ack_at_ms"] == 1080
    assert records[0]["ingestion_to_ack_ms"] == 80


@pytest.mark.parametrize("ingested_at", [None, "1000", True, 1000.5, {"value": 1000}])
def test_debug_accepts_messages_without_a_valid_ingestion_timestamp(
    load_persister, event, ingested_at,
):
    runtime, table, lambda_client = load_persister("True")
    if ingested_at is None:
        event.pop("iot_ingested_at_ms")
    else:
        event["iot_ingested_at_ms"] = ingested_at
    with patch("time.time_ns", side_effect=[1_050_000_000, 1_080_000_000]):
        runtime.lambda_handler(event, None)

    item = table.put_item.call_args.kwargs["Item"]
    assert item["db_write_started_at_ms"] == 1050
    assert "ingestion_to_write_ms" not in item
    lambda_client.invoke.assert_called_once()


def test_failed_write_does_not_log_success_or_invoke_event_checker(load_persister, event, capsys):
    runtime, table, lambda_client = load_persister("True")
    table.put_item.side_effect = RuntimeError("DynamoDB unavailable")
    with patch("time.time_ns", return_value=1_050_000_000) as clock:
        with pytest.raises(RuntimeError, match="DynamoDB unavailable"):
            runtime.lambda_handler(event, None)

    clock.assert_called_once()
    lambda_client.invoke.assert_not_called()
    assert not any(line.startswith("{") for line in capsys.readouterr().out.splitlines())
