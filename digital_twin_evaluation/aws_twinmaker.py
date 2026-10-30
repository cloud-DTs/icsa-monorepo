"""Read telemetry through the TwinMaker API and its deployed data connector."""
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import re

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import valid_value
from .contracts import BackendError, Reading, utc_text


def _timestamp_key(value):
    if not isinstance(value, str):
        raise ValueError("Expected an ISO8601 timestamp")
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})", value)
    if match is None:
        raise ValueError("Expected an ISO8601 timestamp with timezone")
    base, fraction, offset = match.groups()
    second = datetime.fromisoformat(base + offset.replace("Z", "+00:00")).astimezone(timezone.utc)
    return second, (fraction or "").ljust(9, "0")


def timestamps_equal(actual, expected):
    try:
        return _timestamp_key(actual) == _timestamp_key(expected)
    except ValueError:
        return False


class AwsTwinMakerReader:
    def __init__(self, deployment, request_timeout, *, session=None):
        self.deployment = deployment
        config = Config(region_name=deployment.region, connect_timeout=min(3.0, request_timeout),
                        read_timeout=request_timeout, retries={"total_max_attempts": 1, "mode": "standard"})
        try:
            session = session or boto3.Session(region_name=deployment.region)
            self.client = session.client("iottwinmaker", config=config)
        except (BotoCoreError, ClientError) as error:
            raise BackendError(f"Cannot initialize TwinMaker reader: {error}") from error

    def read(self, target, property_name, data_type, timestamp) -> list[Reading]:
        return [reading for page in self.read_pages(target, property_name, data_type, timestamp)
                for reading in page]

    def read_pages(self, target, property_name, data_type, timestamp) -> Iterator[list[Reading]]:
        """Yield each history page so callers can stop before requesting the next one."""
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
        # Native history queries use the deployed entity/component binding.
        # https://docs.aws.amazon.com/iot-twinmaker/latest/apireference/API_GetPropertyValueHistory.html
        request = {"workspaceId": self.deployment.resources.workspace_id,
                   "entityId": target.entity_id, "componentName": target.component_name,
                   "selectedProperties": [property_name], "orderByTime": "DESCENDING", "maxResults": 10,
                   "startTime": utc_text(moment - timedelta(milliseconds=1)),
                   "endTime": utc_text(moment + timedelta(milliseconds=1))}
        seen_tokens = set()
        while True:
            try:
                response = self.client.get_property_value_history(**request)
            except (BotoCoreError, ClientError) as error:
                raise BackendError(f"TwinMaker history read failed: {error}") from error
            entries = response.get("propertyValues")
            if not isinstance(entries, list):
                raise BackendError("Invalid TwinMaker propertyValues list.")
            readings = []
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("entityPropertyReference"), dict):
                    raise BackendError("Invalid TwinMaker property reference.")
                if entry["entityPropertyReference"].get("propertyName") != property_name:
                    continue
                values = entry.get("values", [])
                if not isinstance(values, list):
                    raise BackendError("Invalid TwinMaker history values.")
                for item in values:
                    if not isinstance(item, dict) or not isinstance(item.get("value"), dict):
                        raise BackendError("Invalid TwinMaker history value.")
                    try:
                        _timestamp_key(item.get("time"))
                    except ValueError as error:
                        raise BackendError("Invalid TwinMaker history timestamp.") from error
                    value = item["value"].get(data_type.lower() + "Value")
                    if not valid_value(value, data_type):
                        raise BackendError("TwinMaker returned a value incompatible with the selected property.")
                    readings.append(Reading(item["time"], value))
            yield readings
            token = response.get("nextToken")
            if not token:
                return
            if not isinstance(token, str) or token in seen_tokens:
                raise BackendError("Invalid TwinMaker pagination token.")
            seen_tokens.add(token)
            request["nextToken"] = token
