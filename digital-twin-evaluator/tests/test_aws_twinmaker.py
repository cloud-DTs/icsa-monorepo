from types import SimpleNamespace

import boto3
import pytest
from botocore.stub import Stubber

from digital_twin_evaluation.aws_twinmaker import AwsTwinMakerReader, timestamps_equal
from digital_twin_evaluation.contracts import BackendError, Reading
from digital_twin_evaluation.deployment import load_deployment


TIMESTAMP = "2026-10-22T17:00:00.000Z"


def response(value=0.0, timestamp=TIMESTAMP):
    return {"propertyValues": [{"entityPropertyReference": {"propertyName": "output"},
                                "values": [{"time": timestamp, "value": {"doubleValue": value}}]}]}


def expected_request():
    return {"workspaceId": "MGridICSA-twinmaker", "entityId": "pv-entity", "componentName": "pV1",
            "selectedProperties": ["output"], "startTime": "2026-10-22T16:59:59.999Z",
            "endTime": "2026-10-22T17:00:00.001Z", "orderByTime": "DESCENDING", "maxResults": 10}


@pytest.fixture
def reader(deployment_dir):
    deployment = load_deployment(deployment_dir)
    client = boto3.client("iottwinmaker", region_name="eu-west-1", aws_access_key_id="test", aws_secret_access_key="test")
    calls = []

    def make_client(service, **kwargs):
        calls.append((service, kwargs))
        assert service == "iottwinmaker"  # No direct Lambda or IoT HTTPS client.
        return client

    reader = AwsTwinMakerReader(deployment, 2, session=SimpleNamespace(client=make_client))
    return reader, client, calls, deployment.target("MicroGrid.pv.pV1")


def test_real_sdk_request_uses_deployed_binding_and_a_narrow_time_window(reader):
    reader, client, calls, target = reader
    with Stubber(client) as stub:
        stub.add_response("get_property_value_history", response(), expected_request())
        assert reader.read(target, "output", "DOUBLE", TIMESTAMP) == [Reading(TIMESTAMP, 0.0)]
        stub.assert_no_pending_responses()
    assert len(calls) == 1
    assert calls[0][1]["config"].retries["total_max_attempts"] == 1
    assert calls[0][1]["config"].read_timeout == 2


def test_history_pagination_does_not_hide_the_matching_record(reader):
    reader, client, _, target = reader
    with Stubber(client) as stub:
        stub.add_response("get_property_value_history", {"propertyValues": [], "nextToken": "page2"}, expected_request())
        stub.add_response("get_property_value_history", response(1.25), {**expected_request(), "nextToken": "page2"})
        assert reader.read(target, "output", "DOUBLE", TIMESTAMP) == [Reading(TIMESTAMP, 1.25)]
        stub.assert_no_pending_responses()


def test_access_denied_is_a_read_error_and_does_not_fall_back_to_lambda(reader):
    reader, client, calls, target = reader
    with Stubber(client) as stub:
        stub.add_client_error("get_property_value_history", service_error_code="AccessDeniedException",
                              expected_params=expected_request())
        with pytest.raises(BackendError, match="AccessDenied"):
            reader.read(target, "output", "DOUBLE", TIMESTAMP)
    assert len(calls) == 1


@pytest.mark.parametrize("empty", [{"propertyValues": []}, {"propertyValues": [
    {"entityPropertyReference": {"propertyName": "output"}, "values": []},
]}])
def test_empty_history_is_not_a_backend_failure(reader, empty):
    reader, client, _, target = reader
    with Stubber(client) as stub:
        stub.add_response("get_property_value_history", empty, expected_request())
        assert reader.read(target, "output", "DOUBLE", TIMESTAMP) == []


def test_repeated_pagination_token_is_rejected(reader):
    reader, client, _, target = reader
    with Stubber(client) as stub:
        stub.add_response("get_property_value_history", {"propertyValues": [], "nextToken": "repeat"}, expected_request())
        stub.add_response("get_property_value_history", {"propertyValues": [], "nextToken": "repeat"}, {**expected_request(), "nextToken": "repeat"})
        with pytest.raises(BackendError, match="pagination"):
            reader.read(target, "output", "DOUBLE", TIMESTAMP)


@pytest.mark.parametrize("malformed", [{}, {"propertyValues": {}}, {"propertyValues": [{
    "entityPropertyReference": {"propertyName": "output"}, "values": [{"time": TIMESTAMP, "value": {"doubleValue": True}}],
}]}])
def test_malformed_history_is_not_reported_as_a_visibility_timeout(reader, malformed):
    reader, _, _, target = reader
    reader.client = SimpleNamespace(get_property_value_history=lambda **kwargs: malformed)
    with pytest.raises(BackendError):
        reader.read(target, "output", "DOUBLE", TIMESTAMP)


@pytest.mark.parametrize("actual,expected", [
    ("2026-10-22T17:00:00Z", True),
    ("2026-10-22T19:00:00.000000000+02:00", True),
    ("2026-10-22T17:00:00.000000001Z", False),
    ("2026-10-22T17:00:00.001Z", False),
    ("2026-10-22T17:00:00", False),
    ("invalid", False),
])
def test_timestamp_comparison_preserves_timezone_and_fraction_precision(actual, expected):
    assert timestamps_equal(actual, TIMESTAMP) is expected
