from __future__ import annotations

import json
from threading import Lock

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import valid_value
from .contracts import BackendError, Deployment, Json, Reading, Target


class AwsTelemetryBackend:
    def __init__(
        self, deployment: Deployment, request_timeout: float, *, session=None,
        max_pool_connections: int = 10, mode: str = "storage",
    ):
        self.deployment = deployment
        self.sdk_config = Config(
            region_name=deployment.region,
            connect_timeout=min(3.0, request_timeout),
            read_timeout=request_timeout,
            retries={"total_max_attempts": 1, "mode": "standard"},
            max_pool_connections=max(10, max_pool_connections),
        )
        self.iot_client = None
        self._client_lock = Lock()
        try:
            self.session = session or boto3.Session(region_name=deployment.region)
            self.lambda_client = self.session.client("lambda", config=self.sdk_config)
            if mode == "ingestion":
                self.iot_client = self.session.client("iot-data", config=self.sdk_config)
        except (BotoCoreError, ClientError) as error:
            raise BackendError(f"Cannot initialize AWS evaluation clients: {error}") from error

    def _iot_client(self):
        with self._client_lock:
            if self.iot_client is None:
                self.iot_client = self.session.client("iot-data", config=self.sdk_config)
            return self.iot_client

    def write(self, mode: str, payload: dict[str, Json]) -> None:
        if mode == "storage":
            self._invoke(self.deployment.resources.writer_function, payload)
        elif mode == "ingestion":
            try:
                response = self._iot_client().publish(
                    topic=self.deployment.resources.iot_topic, qos=1, retain=False,
                    payload=json.dumps(payload, allow_nan=False).encode("utf-8"),
                )
            except (BotoCoreError, ClientError) as error:
                raise BackendError(f"IoT publish failed: {error}") from error
            if response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 200:
                raise BackendError("IoT publish did not return HTTP 200.")
        else:
            raise BackendError(f"Unsupported telemetry write mode: {mode}")

    def read(
        self, target: Target, property_name: str, data_type: str, timestamp: str
    ) -> list[Reading]:
        result = self._invoke(self.deployment.resources.reader_function, {
            "workspaceId": self.deployment.resources.workspace_id,
            "entityId": target.entity_id,
            "componentName": target.component_name,
            "selectedProperties": [property_name],
            "properties": {property_name: {"definition": {"dataType": {"type": data_type}}}},
            "startTime": timestamp, "endTime": timestamp,
            "orderByTime": "DESCENDING", "maxResults": 1,
        })
        if not isinstance(result, dict) or not isinstance(result.get("propertyValues"), list):
            raise BackendError("Invalid reader response: expected a propertyValues list.")
        readings = []
        value_key = data_type.lower() + "Value"
        for entry in result["propertyValues"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("values"), list):
                raise BackendError("Invalid reader property values.")
            reference = entry.get("entityPropertyReference")
            if not isinstance(reference, dict) or not isinstance(reference.get("propertyName"), str):
                raise BackendError("Invalid reader property reference.")
            if reference["propertyName"] != property_name:
                continue
            for item in entry["values"]:
                if not isinstance(item, dict) or not isinstance(item.get("time"), str):
                    raise BackendError("Invalid reader record timestamp.")
                value = item.get("value")
                if not isinstance(value, dict) or value_key not in value:
                    raise BackendError(f"Invalid reader record: expected {value_key}.")
                if not valid_value(value[value_key], data_type):
                    raise BackendError("Reader returned a value incompatible with the deployed property type.")
                readings.append(Reading(item["time"], value[value_key]))
        return readings

    def _invoke(self, function_name: str, payload: dict[str, Json]) -> Json:
        try:
            response = self.lambda_client.invoke(
                FunctionName=function_name, InvocationType="RequestResponse",
                Payload=json.dumps(payload, allow_nan=False).encode("utf-8"),
            )
            stream = response.get("Payload")
            if stream is None:
                raise BackendError(f"Lambda {function_name} returned no payload stream.")
            try:
                body = stream.read()
            finally:
                stream.close()
        except (BotoCoreError, ClientError) as error:
            raise BackendError(f"Lambda {function_name} invocation failed: {error}") from error
        if response.get("StatusCode") != 200 or response.get("FunctionError"):
            raise BackendError(
                f"Lambda {function_name} failed: status={response.get('StatusCode')}, "
                f"FunctionError={response.get('FunctionError')}."
            )
        try:
            return json.loads(body)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise BackendError(f"Lambda {function_name} returned invalid JSON.") from error
