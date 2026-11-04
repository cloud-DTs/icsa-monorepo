import importlib
import json
from datetime import datetime, timezone
from threading import Event, Thread
from unittest.mock import Mock

import pytest

from simulator.domain import Attribute, DataType


module = importlib.import_module("simulator.SimulationLoop")


@pytest.fixture
def loop(monkeypatch):
    monkeypatch.setenv("SIMULATOR_MOCK_AWS", "true")
    return module.SimulationLoop("dt/iot-data")


def attribute(name="power"):
    result = Attribute()
    result.name, result.dataType = name, DataType.DOUBLE
    return result


@pytest.mark.parametrize("value", [None, 0, -1, float("nan"), float("inf"), True])
def test_invalid_publish_intervals_are_rejected(loop, value):
    with pytest.raises(ValueError):
        loop.sim_time = value


def test_mock_mode_is_the_default(monkeypatch):
    monkeypatch.delenv("SIMULATOR_MOCK_AWS", raising=False)
    monkeypatch.setattr(module, "_create_iot_client", Mock(side_effect=AssertionError("AWS used by default")))
    assert module.SimulationLoop("dt/iot-data").mock_aws


def test_typo_in_mock_mode_cannot_enable_real_aws(monkeypatch):
    monkeypatch.setenv("SIMULATOR_MOCK_AWS", "truue")
    factory = Mock(side_effect=AssertionError("AWS used with an invalid mock flag"))
    monkeypatch.setattr(module, "_create_iot_client", factory)
    with pytest.raises(ValueError, match="SIMULATOR_MOCK_AWS"):
        module.SimulationLoop("dt/iot-data")
    factory.assert_not_called()


def test_failed_generator_clears_running_state(loop):
    attr = attribute()
    loop.active_runs[attr.id] = {"run": True, "generation": 1, "stop_event": Event()}
    loop._loop(attr, "sensor-a", {"mode": "unsupported"}, 1)
    assert not loop.is_running(attr.id)
    assert "Unsupported" in loop.error_for(attr.id)


def test_stop_wakes_the_worker_without_waiting_for_the_interval(loop, monkeypatch):
    published = Event()
    threads = []

    def make_thread(*args, **kwargs):
        thread = Thread(*args, **kwargs)
        threads.append(thread)
        return thread

    class Client:
        def publish(self, **kwargs):
            published.set()
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    monkeypatch.setattr(module.threading, "Thread", make_thread)
    loop.mock_aws, loop.client = False, Client()
    attr = attribute()
    loop.start_one(attr, "sensor-a", {"mode": "uniform", "min": 1, "max": 1})
    try:
        assert published.wait(1)
    finally:
        loop.stop_one(attr)
    threads[0].join(0.5)
    assert not threads[0].is_alive()


def test_generated_properties_do_not_overwrite_the_same_device_timestamp(loop, monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)

    attrs = [attribute("power"), attribute("capacity")]
    messages = []

    class Client:
        def publish(self, **kwargs):
            message = json.loads(kwargs["payload"])
            messages.append(message)
            loop.stop_one(attrs[len(messages) - 1])
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    monkeypatch.setattr(module, "datetime", Clock)
    loop.mock_aws, loop.client = False, Client()
    for attr in attrs:
        loop.active_runs[attr.id] = {"run": True, "generation": 1, "stop_event": Event()}
        loop._loop(attr, "sensor-a", {"mode": "uniform", "min": 1, "max": 1}, 1)
    assert len({message["time"] for message in messages}) == 2


def test_forecast_only_series_is_not_reported_as_a_current_sample():
    with pytest.raises(ValueError, match="at or before"):
        module.select_current_sample([200, 300], [1, 2], now_epoch=100)
