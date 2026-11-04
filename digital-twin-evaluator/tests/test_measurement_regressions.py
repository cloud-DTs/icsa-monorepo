"""Regression checks for sample timing and paginated visibility reads."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from digital_twin_evaluation.aws import AwsTelemetryBackend
from digital_twin_evaluation.aws_twinmaker import AwsTwinMakerReader
from digital_twin_evaluation.contracts import BackendError
from digital_twin_evaluation.deployment import load_deployment
from test_aws import FakeLambda, FakeSession
from test_mqtt_evaluation import ProcessingClient, mqtt_deployment
from test_mqtt_evaluation import prepare as mqtt_plan
from test_mqtt_twinmaker import Publisher
from test_mqtt_twinmaker import prepare as twinmaker_plan
from test_roundtrip import FakeClock
from test_roundtrip import prepare as roundtrip_plan
from test_roundtrip_targets import prepare as roundtrip_targets_plan


@pytest.mark.parametrize("match_page", [1, 2])
def test_visibility_finishes_on_the_first_matching_history_page(deployment_dir, match_page):
    clock = FakeClock()
    publisher = Publisher(clock)
    requests = []

    def get_history(**request):
        requests.append(request)
        page = len(requests)
        if page > match_page:
            clock.now += 0.200  # A needless page would exceed the deadline.
            return {"propertyValues": []}
        clock.now += 0.030
        payload = publisher.writes[-1][1]
        value = payload["output"] if page == match_page else payload["output"] + 1
        return {"propertyValues": [{
            "entityPropertyReference": {"propertyName": "output"},
            "values": [{"time": payload["time"], "value": {"doubleValue": value}}],
        }], "nextToken": f"page-{page + 1}"}

    session = SimpleNamespace(client=lambda *a, **kw: SimpleNamespace(
        get_property_value_history=get_history,
    ))
    reader = AwsTwinMakerReader(load_deployment(deployment_dir), 1, session=session)
    result = twinmaker_plan(deployment_dir, timeout_seconds=0.1).run(
        client=publisher, reader=reader, clock=clock,
    )
    record = result.measurements[0]
    assert record["status"] == "success"
    assert record["roundtrip_ms"] == pytest.approx(5 + 30 * match_page)
    assert record["read_ms"] == pytest.approx(30 * match_page)
    assert record["response_timestamp"] == record["timestamp"]
    assert record["response_value"] == record["value"]
    assert len(requests) == match_page
    assert record["read_attempts"] == 1


@pytest.mark.parametrize("matching", [False, True])
@pytest.mark.parametrize("at_deadline", [False, True])
def test_history_pagination_stops_at_the_deadline(deployment_dir, matching, at_deadline):
    clock = FakeClock()
    publisher = Publisher(clock)
    requests = []
    publish = publisher.publish
    deadline = None

    def publish_with_deadline(topic, payload):
        nonlocal deadline
        deadline = clock.monotonic() + 0.1
        return publish(topic, payload)

    publisher.publish = publish_with_deadline

    def get_history(**request):
        requests.append(request)
        if at_deadline:
            clock.now = deadline
        else:
            clock.now += 0.150
        if len(requests) > 1:
            return {"propertyValues": []}
        payload = publisher.writes[-1][1]
        values = [{"time": payload["time"], "value": {"doubleValue": payload["output"]}}] if matching else []
        return {"propertyValues": [{
            "entityPropertyReference": {"propertyName": "output"}, "values": values,
        }], "nextToken": "page-2"}

    session = SimpleNamespace(client=lambda *a, **kw: SimpleNamespace(
        get_property_value_history=get_history,
    ))
    reader = AwsTwinMakerReader(load_deployment(deployment_dir), 1, session=session)
    result = twinmaker_plan(deployment_dir, timeout_seconds=0.1).run(
        client=publisher, reader=reader, clock=clock,
    )
    record = result.measurements[0]
    assert record["status"] == ("success" if matching and at_deadline else "timeout")
    assert len(requests) == 1
    assert record["roundtrip_ms"] == pytest.approx(100 if at_deadline else 155)
    assert record["read_ms"] == pytest.approx(95 if at_deadline else 150)


@pytest.mark.parametrize("multiple_targets", [False, True])
def test_sequential_ingestion_client_setup_is_outside_sample_timing(deployment_dir, multiple_targets):
    clock = FakeClock()

    class SlowClientSetup(FakeSession):
        def client(self, service, **kwargs):
            if service == "iot-data":
                clock.now += 0.250
            return super().client(service, **kwargs)

    session = SlowClientSetup()

    def invoke(**request):
        payload = json.loads(session.iot_client.calls[-1]["payload"])
        query = json.loads(request["Payload"])
        prop = query["selectedProperties"][0]
        session.lambda_client.result = {"propertyValues": [{
            "entityPropertyReference": {"propertyName": prop},
            "values": [{"time": payload["time"], "value": {"doubleValue": payload[prop]}}],
        }]}
        return FakeLambda.invoke(session.lambda_client, **request)

    session.lambda_client.invoke = invoke

    def backend_factory(deployment, request_timeout, **kwargs):
        return AwsTelemetryBackend(deployment, request_timeout, session=session, **kwargs)

    prepare = roundtrip_targets_plan if multiple_targets else roundtrip_plan
    with patch("digital_twin_evaluation.aws.AwsTelemetryBackend", side_effect=backend_factory):
        result = prepare(deployment_dir, mode="ingestion", samples=1, warmup=0).run(clock=clock)
    assert result.successful
    assert len(result.measurements) == (2 if multiple_targets else 1)
    assert all(record["roundtrip_ms"] == pytest.approx(0) for record in result.measurements)
    assert [service for service, _ in session.calls] == ["lambda", "iot-data"]


def test_sync_mqtt_publish_error_preserves_elapsed_write_time(mqtt_deployment):
    clock = FakeClock()

    def fail(client, payload, future):
        clock.now += 0.020
        raise BackendError("synchronous publish failure")

    client = ProcessingClient(clock, fail)
    result = mqtt_plan(mqtt_deployment).run(client=client, clock=clock)
    record = result.measurements[0]
    assert record["status"] == "write_error"
    assert record["roundtrip_ms"] == pytest.approx(25)
    assert record["write_ms"] == pytest.approx(25)
    assert client.closed
