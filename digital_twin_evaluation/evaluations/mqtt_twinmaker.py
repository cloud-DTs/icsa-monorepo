"""Client MQTT publish to the first verified native TwinMaker history response."""
from dataclasses import asdict, dataclass, field
from datetime import timedelta, timezone
import math
import re
import secrets
from threading import Lock
from uuid import uuid4

from ..aws_twinmaker import timestamps_equal
from ..config import integer, positive_number, valid_value
from ..contracts import BackendError, Deployment, RunResult, SystemClock, Target, utc_text
from ..deployment import require_text
from ..statistics import distribution, summarize


@dataclass(frozen=True)
class MqttTwinMakerOptions:
    property: str
    value_range: tuple[float, float]
    endpoint: str | None
    samples: int
    warmup: int
    timeout_seconds: float
    poll_interval_seconds: float
    request_timeout_seconds: float
    setup_timeout_seconds: float


class MqttTwinMakerEvaluation:
    def prepare(self, deployment, parameters):
        allowed = {"target", "property", "value_range", "endpoint", "samples", "warmup", "timeout_seconds",
                   "poll_interval_seconds", "request_timeout_seconds", "setup_timeout_seconds", "concurrency"}
        if unknown := set(parameters) - allowed:
            raise ValueError(f"Unknown mqtt-twinmaker parameters: {', '.join(sorted(unknown))}")
        if integer(parameters.get("concurrency", 1), "concurrency", 1) != 1:
            raise ValueError("mqtt-twinmaker currently requires concurrency 1.")
        target = deployment.target(require_text(parameters.get("target"), "target"))
        prop = require_text(parameters.get("property"), "property")
        if prop in ("iotDeviceId", "time") or target.property_type(prop) != "DOUBLE":
            raise ValueError("mqtt-twinmaker requires a deployed DOUBLE telemetry property.")
        bounds = parameters.get("value_range")
        if not isinstance(bounds, list) or len(bounds) != 2 or any(type(v) not in (int, float) for v in bounds):
            raise ValueError("value_range must contain two finite numeric bounds.")
        try:
            lower, upper = map(float, bounds)
        except OverflowError as error:
            raise ValueError("value_range bounds must be finite.") from error
        if not all(math.isfinite(v) for v in (lower, upper, upper - lower)) or lower >= upper:
            raise ValueError("value_range requires finite lower < upper.")
        if (upper - lower) / max(math.ulp(lower), math.ulp(upper)) < 2**40:
            raise ValueError("value_range is too narrow for reliable unique-value correlation.")
        endpoint = parameters.get("endpoint")
        if endpoint is not None and (not isinstance(endpoint, str) or len(endpoint) > 253
                or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", endpoint)):
            raise ValueError("endpoint must be a host name without a URL scheme, port, or path.")
        return MqttTwinMakerPlan(deployment, target, MqttTwinMakerOptions(
            property=prop, value_range=(lower, upper), endpoint=endpoint,
            samples=integer(parameters.get("samples", 100), "samples", 1),
            warmup=integer(parameters.get("warmup", 10), "warmup", 0),
            timeout_seconds=positive_number(parameters.get("timeout_seconds", 10), "timeout_seconds"),
            poll_interval_seconds=positive_number(parameters.get("poll_interval_seconds", 0.1), "poll_interval_seconds"),
            request_timeout_seconds=positive_number(parameters.get("request_timeout_seconds", 10), "request_timeout_seconds"),
            setup_timeout_seconds=positive_number(parameters.get("setup_timeout_seconds", 10), "setup_timeout_seconds"),
        ))


@dataclass
class _Connection:
    lock: Lock = field(default_factory=Lock)
    error: str | None = None

    def interrupted(self, error):
        with self.lock:
            self.error = str(error)

    def problem(self, acknowledgement):
        with self.lock:
            if self.error is not None:
                return "connection_error", self.error
            if acknowledgement["error"] is not None:
                return "write_error", acknowledgement["error"]
        return None

    def acknowledged(self, future, acknowledgement, clock, started):
        observed = clock.monotonic()
        try:
            future.result()
        except Exception as error:
            with self.lock:
                acknowledgement["error"] = str(error)
        else:
            with self.lock:
                acknowledgement["ms"] = (observed - started) * 1000


@dataclass(frozen=True)
class MqttTwinMakerPlan:
    deployment: Deployment
    target: Target
    options: MqttTwinMakerOptions

    def describe(self):
        return {
            "schema_version": 1, "evaluation": "mqtt-twinmaker", "twin_name": self.deployment.twin_name,
            "region": self.deployment.region,
            "source": {"adapter": "manager-state-v1", "fingerprint": self.deployment.fingerprint,
                       "applied_at": self.deployment.applied_at},
            "target": {"path": self.target.path, "entity_id": self.target.entity_id,
                       "component_name": self.target.component_name, "device_id": self.target.device_id,
                       "property": self.options.property, "data_type": "DOUBLE"},
            "parameters": asdict(self.options), "publish_topic": self.deployment.resources.iot_topic,
            "workspace_id": self.deployment.resources.workspace_id, "read_api": "GetPropertyValueHistory",
            "transport": "MQTT 3.1.1 over WSS with SigV4; native TwinMaker HTTPS read",
            "qos": 1, "client_count": 1, "concurrency": 1,
            "correlation": "sent_timestamp_and_unique_value",
            "latency_scope": "before client MQTT publish to first matching TwinMaker history response; includes polling and read latency; excludes setup",
            "timeout_scope": "whole_cycle; an in-flight SDK history read can exceed the deadline",
            "read_consistency": "deployed TwinMaker connector default; no consistency settings are changed",
            "visibility_scope": "TwinMaker API availability; Grafana datasource and panel rendering are not measured",
            "clock_scope": "one client monotonic clock; UTC timestamps identify records only",
            "requirements": ["One writer for the selected property", "Existing TwinMaker history connector"],
        }

    def _values(self):
        lower, upper = self.options.value_range
        values, used = [], set()
        for _ in range(self.options.samples + self.options.warmup):
            for _ in range(64):
                value = lower + (upper - lower) * (secrets.randbits(52) / 2**52)
                if value not in used:
                    values.append(value)
                    used.add(value)
                    break
            else:
                raise ValueError("Cannot allocate unique values in value_range.")
        return values

    def run(self, *, client=None, reader=None, clock=None):
        clock = clock or SystemClock()
        values = self._values()
        if reader is None:
            from ..aws_twinmaker import AwsTwinMakerReader
            reader = AwsTwinMakerReader(self.deployment, self.options.request_timeout_seconds)
        if client is None:
            from ..mqtt import AwsMqttClient
            client = AwsMqttClient(self.deployment.region, self.options.endpoint, self.options.setup_timeout_seconds)
        connection = _Connection()
        records, previous = [], None
        run_id, started = uuid4().hex, utc_text(clock.utcnow())
        cleanup_error = None
        try:
            client.connect(connection.interrupted)
            for sequence, value in enumerate(values):
                moment = clock.utcnow().astimezone(timezone.utc)
                moment = moment.replace(microsecond=moment.microsecond // 1000 * 1000)
                if previous is not None and moment <= previous:
                    moment = previous + timedelta(milliseconds=1)
                previous = moment
                phase = "warmup" if sequence < self.options.warmup else "measured"
                records.append(self._sample(client, reader, clock, connection, run_id, sequence, phase, utc_text(moment), value))
        finally:
            try:
                client.close()
            except BackendError as error:
                cleanup_error = str(error)
        summary = summarize(records)
        summary["publish_ack_ms"] = distribution([r["publish_ack_ms"] for r in records
            if r["phase"] == "measured" and r["status"] == "success" and r["publish_ack_ms"] is not None])
        if cleanup_error:
            summary["cleanup_error"] = cleanup_error
        plan = self.describe()
        plan["resolved_endpoint"] = getattr(client, "endpoint", None)
        return RunResult(evaluation="mqtt-twinmaker", twin_name=self.deployment.twin_name, run_id=run_id,
                         started_at=started, finished_at=utc_text(clock.utcnow()),
                         successful=summary["failed_samples"] == 0, plan=plan, summary=summary, measurements=records)

    def _sample(self, client, reader, clock, connection, run_id, sequence, phase, timestamp, value):
        payload = {"iotDeviceId": self.target.device_id, "time": timestamp, self.options.property: value}
        started = clock.monotonic()
        deadline = started + self.options.timeout_seconds
        acknowledgement = {"error": None, "ms": None}
        record = {"run_id": run_id, "sequence": sequence, "phase": phase, "target": self.target.path,
                  "property": self.options.property, "device_id": self.target.device_id, "timestamp": timestamp,
                  "value": value, "response_value": None, "response_timestamp": None,
                  "status": "timeout", "error": "", "write_ms": 0.0, "read_ms": 0.0,
                  "read_attempts": 0, "publish_ack_ms": None, "roundtrip_ms": 0.0}
        if problem := connection.problem(acknowledgement):
            record.update(status=problem[0], error=problem[1])
        else:
            try:
                future = client.publish(self.deployment.resources.iot_topic, payload)
            except BackendError as error:
                record.update(status="write_error", error=str(error))
                record["write_ms"] = (clock.monotonic() - started) * 1000
            else:
                record["write_ms"] = (clock.monotonic() - started) * 1000
                future.add_done_callback(lambda f: connection.acknowledged(f, acknowledgement, clock, started))
                self._poll(reader, record, clock, deadline, connection, acknowledgement)
        record["roundtrip_ms"] = (clock.monotonic() - started) * 1000
        with connection.lock:
            record["publish_ack_ms"] = acknowledgement["ms"]
        if record["status"] == "timeout":
            record["error"] = "TwinMaker did not return the sent timestamp and value before the deadline."
        return record

    def _poll(self, reader, record, clock, deadline, connection, acknowledgement):
        while clock.monotonic() < deadline:
            if problem := connection.problem(acknowledgement):
                record.update(status=problem[0], error=problem[1])
                return
            read_started = clock.monotonic()
            record["read_attempts"] += 1
            try:
                for readings in reader.read_pages(self.target, self.options.property, "DOUBLE", record["timestamp"]):
                    if problem := connection.problem(acknowledgement):
                        record.update(status=problem[0], error=problem[1])
                        return
                    if clock.monotonic() > deadline:
                        return
                    for reading in readings:
                        if (timestamps_equal(reading.timestamp, record["timestamp"])
                                and valid_value(reading.value, "DOUBLE") and reading.value == record["value"]):
                            record.update(status="success", response_value=reading.value, response_timestamp=reading.timestamp)
                            return
                    if clock.monotonic() >= deadline:
                        return
            except BackendError as error:
                record.update(status="read_error", error=str(error))
                return
            finally:
                record["read_ms"] += (clock.monotonic() - read_started) * 1000
            remaining = deadline - clock.monotonic()
            if remaining > 0:
                clock.sleep(min(self.options.poll_interval_seconds, remaining))
