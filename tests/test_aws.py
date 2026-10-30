import io
import json

import pytest
from botocore.exceptions import NoCredentialsError

from digital_twin_evaluation.aws import AwsTelemetryBackend
from digital_twin_evaluation.contracts import BackendError, Reading
from digital_twin_evaluation.deployment import load_deployment


class FakeLambda:
    def __init__(self):
        self.calls = []
        self.status = 200
        self.function_error = None
        self.result = None

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        response = {"StatusCode": self.status, "Payload": io.BytesIO(json.dumps(self.result).encode())}
        if self.function_error:
            response["FunctionError"] = self.function_error
        return response


class FakeIoT:
    def __init__(self):
        self.calls = []

    def publish(self, **kwargs):
        self.calls.append(kwargs)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


class FakeSession:
    def __init__(self):
        self.lambda_client = FakeLambda()
        self.iot_client = FakeIoT()
        self.calls = []

    def client(self, service, **kwargs):
        self.calls.append((service, kwargs))
        return self.lambda_client if service == "lambda" else self.iot_client


def backend_for(deployment_dir):
    session = FakeSession()
    backend = AwsTelemetryBackend(load_deployment(deployment_dir), 3, session=session)
    return backend, session


def test_storage_writer_is_synchronous_and_uses_the_payload_unchanged(deployment_dir):
    backend, session = backend_for(deployment_dir)
    payload = {"iotDeviceId": "pv-sensor", "time": "time", "output": 12.5}
    backend.write("storage", payload)
    call = session.lambda_client.calls[0]
    assert call["FunctionName"] == "MGridICSA-persister"
    assert call["InvocationType"] == "RequestResponse"
    assert json.loads(call["Payload"]) == payload
    sdk_config = session.calls[0][1]["config"]
    assert sdk_config.retries["total_max_attempts"] == 1
    assert sdk_config.read_timeout == 3


def test_missing_credentials_are_a_backend_error(deployment_dir):
    class MissingCredentials:
        def client(self, *args, **kwargs):
            raise NoCredentialsError()
    with pytest.raises(BackendError, match="credentials"):
        AwsTelemetryBackend(load_deployment(deployment_dir), 3, session=MissingCredentials())


def test_reader_queries_the_exact_sent_timestamp_and_deployed_binding(deployment_dir):
    backend, session = backend_for(deployment_dir)
    target = load_deployment(deployment_dir).target("MicroGrid.pv.pV1")
    session.lambda_client.result = {"propertyValues": [{
        "entityPropertyReference": {"propertyName": "output"},
        "values": [{"time": "exact-time", "value": {"doubleValue": 0.0}}],
    }]}
    assert backend.read(target, "output", "DOUBLE", "exact-time") == [Reading("exact-time", 0.0)]
    call = session.lambda_client.calls[0]
    assert call["FunctionName"] == "MGridICSA-hot-reader"
    payload = json.loads(call["Payload"])
    assert payload["workspaceId"] == "MGridICSA-twinmaker"
    assert payload["entityId"] == "pv-entity"
    assert payload["componentName"] == "pV1"
    assert payload["startTime"] == payload["endTime"] == "exact-time"
    assert payload["selectedProperties"] == ["output"]
    assert payload["maxResults"] == 1


def test_ingestion_publishes_once_to_the_twin_topic(deployment_dir):
    backend, session = backend_for(deployment_dir)
    payload = {"iotDeviceId": "pv-sensor", "time": "time", "output": -2.0}
    backend.write("ingestion", payload)
    call = session.iot_client.calls[0]
    assert call["topic"] == "MGridICSA/iot-data"
    assert call["qos"] == 1
    assert call["retain"] is False
    assert json.loads(call["payload"]) == payload
    assert session.lambda_client.calls == []


@pytest.mark.parametrize("status,error", [(202, None), (200, "Unhandled")])
def test_http_success_does_not_hide_a_lambda_failure(deployment_dir, status, error):
    backend, session = backend_for(deployment_dir)
    session.lambda_client.status = status
    session.lambda_client.function_error = error
    session.lambda_client.result = {"errorMessage": "failed"}
    with pytest.raises(BackendError):
        backend.write("storage", {})


@pytest.mark.parametrize("result", [None, {}, {"propertyValues": {}}, {"propertyValues": [{"values": "bad"}]}])
def test_malformed_reader_responses_fail_instead_of_becoming_timeouts(deployment_dir, result):
    backend, session = backend_for(deployment_dir)
    session.lambda_client.result = result
    target = load_deployment(deployment_dir).target("MicroGrid.pv.pV1")
    with pytest.raises(BackendError):
        backend.read(target, "output", "DOUBLE", "time")
