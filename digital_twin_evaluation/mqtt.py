"""AWS MQTT transport. Connection setup is outside measured message cycles."""
from __future__ import annotations

from concurrent.futures import Future
import json
from threading import Lock
import time
from uuid import uuid4

from .contracts import BackendError, Json


def _build_connection(*, region, endpoint, timeout, on_interrupted):
    # Official SDK supports signed MQTT over WSS with the AWS credential chain.
    # https://aws.github.io/aws-iot-device-sdk-python-v2/awsiot/mqtt_connection_builder.html
    from awscrt import auth
    from awsiot import mqtt_connection_builder

    return mqtt_connection_builder.websockets_with_default_aws_signing(
        endpoint=endpoint, region=region,
        credentials_provider=auth.AwsCredentialsProvider.new_default_chain(),
        client_id=f"dt-eval-{uuid4().hex}", clean_session=True,
        keep_alive_secs=30, tcp_connect_timeout_ms=max(1, int(timeout * 1000)),
        protocol_operation_timeout_ms=max(1, int(timeout * 1000)),
        on_connection_interrupted=on_interrupted,
    )


class AwsMqttClient:
    def __init__(self, region: str, endpoint: str | None, setup_timeout_seconds: float):
        self.region = region
        self.endpoint = endpoint
        self.timeout = setup_timeout_seconds
        self.connection = None
        self._ready = False
        self._failure: BackendError | None = None
        self._disconnect_future = None
        self._lock = Lock()

    def start(self, topic: str, on_message, on_disconnect) -> None:
        self._start(topic, on_message, on_disconnect)

    def connect(self, on_disconnect) -> None:
        """Connect for publishing without requiring an MQTT feedback subscription."""
        self._start(None, None, on_disconnect)

    def _start(self, topic, on_message, on_disconnect) -> None:
        from awscrt.mqtt import QoS

        def interrupted(connection, error, **kwargs):
            failure = BackendError(f"MQTT connection interrupted: {error}")
            with self._lock:
                self._failure = failure
                self._ready = False
            # Stop automatic reconnect and replay after a measured connection loss.
            # This call is asynchronous; never wait inside an SDK callback.
            try:
                self._disconnect_future = connection.disconnect()
            except Exception:
                pass  # close() will make another bounded cleanup attempt.
            on_disconnect(failure)

        def received(topic, payload, retain=False, **kwargs):
            on_message(topic, payload, retain)

        try:
            if self.endpoint is None:
                import boto3
                from botocore.config import Config
                config = Config(
                    connect_timeout=min(3, self.timeout), read_timeout=self.timeout,
                    retries={"total_max_attempts": 1},
                )
                self.endpoint = boto3.Session(region_name=self.region).client(
                    "iot", config=config,
                ).describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
            self.connection = _build_connection(
                region=self.region, endpoint=self.endpoint, timeout=self.timeout,
                on_interrupted=interrupted,
            )
            deadline = time.monotonic() + self.timeout
            self.connection.connect().result(timeout=self.timeout)
            if topic is not None:
                future, _ = self.connection.subscribe(
                    topic=topic, qos=QoS.AT_LEAST_ONCE, callback=received,
                )
                # subscribe() completes on SUBACK, not on merely sending SUBSCRIBE.
                # https://awslabs.github.io/aws-crt-python/api/mqtt.html
                result = future.result(timeout=max(0, deadline - time.monotonic()))
                if result.get("qos") != QoS.AT_LEAST_ONCE:
                    raise BackendError("MQTT subscription did not grant QoS 1.")
            with self._lock:
                if self._failure:
                    raise self._failure
                self._ready = True
        except TimeoutError as error:
            raise BackendError("MQTT connection or subscription timed out.") from error
        except BackendError:
            raise
        except Exception as error:
            raise BackendError(f"Cannot start MQTT evaluation client: {error}") from error

    def publish(self, topic: str, payload: dict[str, Json]) -> Future:
        from awscrt.mqtt import QoS

        with self._lock:
            if self._failure:
                raise self._failure
            if not self._ready:
                raise BackendError("MQTT client is not connected and ready.")
            try:
                future, _ = self.connection.publish(
                    topic=topic, qos=QoS.AT_LEAST_ONCE, retain=False,
                    payload=json.dumps(payload, allow_nan=False).encode("utf-8"),
                )
            except Exception as error:
                raise BackendError(f"MQTT publish failed: {error}") from error
        return future

    def close(self) -> None:
        with self._lock:
            self._ready = False
        if self.connection is not None:
            try:
                future = self._disconnect_future or self.connection.disconnect()
                future.result(timeout=self.timeout)
            except Exception as error:
                raise BackendError(f"MQTT disconnect failed: {error}") from error
