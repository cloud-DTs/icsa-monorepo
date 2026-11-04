import copy
import importlib.util
import json
from pathlib import Path

import pytest


HANDLER = Path(__file__).resolve().parents[1] / "demo-code/checkwatt/mqtt-probe/lambda_function.py"


@pytest.fixture
def handler():
    spec = importlib.util.spec_from_file_location("checkwatt_mqtt_probe", HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.lambda_handler


@pytest.mark.parametrize("value", [0.0, -1.25, 1.1234567890123457])
def test_probe_echoes_the_exact_input_value_without_changing_the_event(handler, value):
    event = {"e": {"action": {"functionName": "mqttProbe"}}, "powerKW": value}
    original = copy.deepcopy(event)

    result = json.loads(json.dumps(handler(event, None), allow_nan=False))

    assert result == {"mock": True, "action": "mqttProbe", "value": value}
    assert event == original


@pytest.mark.parametrize("value", [None, True, "1.5", float("nan"), float("inf"), float("-inf")])
def test_probe_rejects_values_that_cannot_be_correlated(handler, value):
    with pytest.raises(ValueError, match="powerKW must be a finite number"):
        handler({"powerKW": value}, None)


def test_probe_rejects_a_missing_input(handler):
    with pytest.raises(ValueError, match="powerKW must be a finite number"):
        handler({}, None)
