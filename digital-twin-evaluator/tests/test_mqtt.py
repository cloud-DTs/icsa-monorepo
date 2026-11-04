from concurrent.futures import Future
from unittest.mock import patch

import pytest

from digital_twin_evaluation.contracts import BackendError
from digital_twin_evaluation.mqtt import AwsMqttClient


def completed(value=None, error=None):
    future = Future()
    if error:
        future.set_exception(error)
    else:
        future.set_result(value)
    return future


class Connection:
    def __init__(self):
        self.calls = []
        self.subscribe_future = completed({"qos": 1})

    def connect(self):
        self.calls.append("connect")
        return completed({"session_present": False})

    def subscribe(self, **kwargs):
        self.calls.append(("subscribe", kwargs))
        self.callback = kwargs["callback"]
        return self.subscribe_future, 1

    def publish(self, **kwargs):
        self.calls.append(("publish", kwargs))
        return completed({"packet_id": 2}), 2

    def disconnect(self):
        self.calls.append("disconnect")
        return completed({})


def test_connect_and_suback_precede_publish_and_sdk_uses_qos_one():
    connection = Connection()
    messages = []
    with patch("digital_twin_evaluation.mqtt._build_connection", return_value=connection):
        client = AwsMqttClient("eu-west-1", "example.iot.eu-west-1.amazonaws.com", 1)
        client.start("reply/topic", lambda *args: messages.append(args), lambda error: None)
        future = client.publish("input/topic", {"power": 1.5})
        assert future.result()["packet_id"] == 2
        connection.callback(topic="reply/topic", payload=b"{}", retain=False, dup=False, qos=1)
        client.close()
    assert connection.calls[0] == "connect"
    assert connection.calls[1][0] == "subscribe"
    assert connection.calls[2][1]["qos"] == 1
    assert connection.calls[2][1]["retain"] is False
    assert messages == [("reply/topic", b"{}", False)]
    assert connection.calls[-1] == "disconnect"


def test_publish_only_connection_does_not_subscribe():
    connection = Connection()
    with patch("digital_twin_evaluation.mqtt._build_connection", return_value=connection):
        client = AwsMqttClient("eu-west-1", "example.iot.eu-west-1.amazonaws.com", 1)
        client.connect(lambda error: None)
        client.publish("input/topic", {"power": 1.5}).result()
        client.close()
    assert connection.calls[0] == "connect"
    assert not any(isinstance(call, tuple) and call[0] == "subscribe" for call in connection.calls)
    assert connection.calls[1][0] == "publish"


def test_publish_only_connection_preserves_sticky_disconnect_failure():
    connection = Connection()
    failures = []
    with patch("digital_twin_evaluation.mqtt._build_connection", return_value=connection) as build:
        client = AwsMqttClient("eu-west-1", "example.iot.eu-west-1.amazonaws.com", 1)
        client.connect(failures.append)
        build.call_args.kwargs["on_interrupted"](connection=connection, error=RuntimeError("lost"))
        with pytest.raises(BackendError, match="lost"):
            client.publish("input/topic", {})
        client.close()
    assert len(failures) == 1


def test_rejected_suback_prevents_publish():
    connection = Connection()
    connection.subscribe_future = completed(error=RuntimeError("denied"))
    with patch("digital_twin_evaluation.mqtt._build_connection", return_value=connection):
        client = AwsMqttClient("eu-west-1", "example.iot.eu-west-1.amazonaws.com", 1)
        with pytest.raises(BackendError, match="denied"):
            client.start("reply/topic", lambda *a: None, lambda e: None)
        with pytest.raises(BackendError):
            client.publish("input/topic", {})
        client.close()
    assert all(not isinstance(c, tuple) or c[0] != "publish" for c in connection.calls)


def test_pending_suback_has_a_bounded_startup_timeout():
    connection = Connection()
    connection.subscribe_future = Future()
    with patch("digital_twin_evaluation.mqtt._build_connection", return_value=connection):
        client = AwsMqttClient("eu-west-1", "example.iot.eu-west-1.amazonaws.com", 0.005)
        with pytest.raises(BackendError, match="timeout|timed out"):
            client.start("reply/topic", lambda *a: None, lambda e: None)
        client.close()


def test_disconnect_is_sticky_and_cannot_silently_queue_another_publish():
    connection = Connection()
    failures = []
    with patch("digital_twin_evaluation.mqtt._build_connection", return_value=connection) as build:
        client = AwsMqttClient("eu-west-1", "example.iot.eu-west-1.amazonaws.com", 1)
        client.start("reply/topic", lambda *a: None, failures.append)
        build.call_args.kwargs["on_interrupted"](connection=connection, error=RuntimeError("lost"))
        with pytest.raises(BackendError, match="lost"):
            client.publish("input/topic", {})
        client.close()
    assert len(failures) == 1


def test_actual_sdk_builder_uses_signed_websockets_without_opening_a_socket():
    connection = Connection()
    with patch("awsiot.mqtt_connection_builder.websockets_with_default_aws_signing", return_value=connection) as builder:
        client = AwsMqttClient("eu-west-1", "example.iot.eu-west-1.amazonaws.com", 2)
        client.start("reply/topic", lambda *a: None, lambda e: None)
        client.close()
    args = builder.call_args.kwargs
    assert args["region"] == "eu-west-1"
    assert args["clean_session"] is True
    assert args["client_id"].startswith("dt-eval-")
    assert args["credentials_provider"] is not None


def test_endpoint_discovery_is_read_only_and_only_at_startup():
    connection = Connection()
    with patch("boto3.Session") as session, patch("digital_twin_evaluation.mqtt._build_connection", return_value=connection) as build:
        session.return_value.client.return_value.describe_endpoint.return_value = {"endpointAddress": "resolved.iot.eu-west-1.amazonaws.com"}
        client = AwsMqttClient("eu-west-1", None, 1)
        session.assert_not_called()
        client.start("reply/topic", lambda *a: None, lambda e: None)
        client.close()
    assert build.call_args.kwargs["endpoint"] == "resolved.iot.eu-west-1.amazonaws.com"
