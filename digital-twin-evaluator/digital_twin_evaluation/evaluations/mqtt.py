"""Client MQTT -> existing processing -> client MQTT, correlated by echoed value."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta, timezone
import json
import secrets
from threading import Event, Lock
from uuid import uuid4

from ..config import valid_value
from ..contracts import BackendError, Deployment, Json, RunResult, SystemClock, Target, utc_text
from ..statistics import distribution, summarize
from .mqtt_config import MqttOptions, resolve_options


class MqttEvaluation:
    def prepare(self, deployment: Deployment, parameters: dict[str, Json]) -> MqttPlan:
        target, options = resolve_options(deployment, parameters)
        return MqttPlan(deployment, target, options)


@dataclass
class _Pending:
    value: float
    started: float
    deadline: float
    done: Event = field(default_factory=Event)
    status: str = "pending"
    error: str = ""
    received_at: float | None = None
    response_value: Json = None
    publish_ack_ms: float | None = None


def _path_value(document, path):
    for key in path:
        if isinstance(document, str):
            document = json.loads(document)
        if not isinstance(document, dict) or key not in document:
            return None
        document = document[key]
    return document


class _Replies:
    def __init__(self, options, clock):
        self.options, self.clock = options, clock
        self.lock = Lock()
        self.active = None
        self.finished = {}
        self.failure = None
        self.counts = dict(matched=0, ignored=0, invalid=0, duplicate=0, late=0)

    def received(self, topic, payload, retain=False):
        received_at = self.clock.monotonic()
        if topic != self.options.response_topic or retain:
            with self.lock:
                self.counts["ignored"] += 1
            return
        try:
            if not isinstance(payload, (bytes, bytearray)) or len(payload) > 131072:
                raise ValueError("Invalid MQTT payload length or type")
            document = json.loads(payload)
            if not isinstance(document, dict):
                raise ValueError("Expected a JSON object")
            value = _path_value(document, self.options.response_value_path)
        except (ValueError, UnicodeError, RecursionError):
            with self.lock:
                self.counts["invalid"] += 1
            return
        with self.lock:
            if not valid_value(value, "DOUBLE") or any(
                k not in document or type(document[k]) is not type(v) or document[k] != v
                for k, v in self.options.response_match.items()
            ):
                self.counts["ignored"] += 1
                return
            active = self.active
            if value in self.finished or (active and value == active.value and active.status == "success"):
                previous_status = self.finished.get(value, "success")
                self.counts["duplicate" if previous_status == "success" else "late"] += 1
            elif active and value == active.value and active.status == "pending":
                if active.started <= received_at <= active.deadline:
                    active.received_at = received_at
                    active.response_value = value
                    active.status = "success"
                    self.counts["matched"] += 1
                    active.done.set()
                else:
                    self.counts["late"] += 1
            else:
                self.counts["ignored"] += 1

    def disconnected(self, error):
        with self.lock:
            self.failure = str(error)
            if self.active and self.active.status == "pending":
                self.active.status = "connection_error"
                self.active.error = self.failure
                self.active.done.set()

    def acknowledged(self, pending, future):
        observed_at = self.clock.monotonic()
        try:
            future.result()
        except Exception as error:
            with self.lock:
                if pending.status == "pending":
                    pending.status, pending.error = "write_error", str(error)
                    pending.done.set()
        else:
            with self.lock:
                pending.publish_ack_ms = (observed_at - pending.started) * 1000


@dataclass(frozen=True)
class MqttPlan:
    deployment: Deployment
    target: Target
    options: MqttOptions

    def describe(self):
        return {
            "schema_version": 1, "evaluation": "mqtt",
            "twin_name": self.deployment.twin_name, "region": self.deployment.region,
            "source": {"adapter": "manager-state-v1", "fingerprint": self.deployment.fingerprint,
                       "applied_at": self.deployment.applied_at,
                       "feedback_fingerprint": self.options.feedback_fingerprint},
            "target": {"path": self.target.path, "device_id": self.target.device_id,
                       "property": self.options.property, "data_type": "DOUBLE"},
            "parameters": asdict(self.options),
            "publish_topic": self.deployment.resources.iot_topic,
            "response_topic": self.options.response_topic,
            "endpoint_source": "explicit" if self.options.endpoint else "read-only IoT endpoint discovery at run startup",
            "transport": "MQTT 3.1.1 over WSS with SigV4", "qos": 1, "client_count": 1,
            "concurrency": 1, "correlation": "unique_sent_value",
            "latency_scope": "before client publish to matching processing reply in MQTT callback; excludes setup",
            "requirements": ["Existing MQTT processing feedback must echo the exact sent DOUBLE value",
                             "Use a value range that triggers the selected action",
                             "One writer for the target and no overlapping control cycles"],
        }

    def _values(self):
        lower, upper = self.options.value_range
        values, used = [], set()
        for _ in range(self.options.samples + self.options.warmup):
            for attempt in range(64):
                value = lower + (upper - lower) * (secrets.randbits(52) / 2**52)
                if value not in used:
                    used.add(value)
                    values.append(value)
                    break
            else:
                raise ValueError("Cannot allocate unique values in value_range.")
        return values

    def run(self, *, client=None, clock=None) -> RunResult:
        clock = clock or SystemClock()
        values = self._values()
        if client is None:
            from ..mqtt import AwsMqttClient
            client = AwsMqttClient(self.deployment.region, self.options.endpoint, self.options.setup_timeout_seconds)
        replies = _Replies(self.options, clock)
        run_id = uuid4().hex
        started = utc_text(clock.utcnow())
        records, previous = [], None
        cleanup_error = None
        try:
            client.start(self.options.response_topic, replies.received, replies.disconnected)
            for sequence, value in enumerate(values):
                moment = clock.utcnow().astimezone(timezone.utc)
                moment = moment.replace(microsecond=moment.microsecond // 1000 * 1000)
                if previous is not None and moment <= previous:
                    moment = previous + timedelta(milliseconds=1)
                previous = moment
                phase = "warmup" if sequence < self.options.warmup else "measured"
                records.append(self._sample(client, replies, clock, run_id, sequence, phase, utc_text(moment), value))
        finally:
            try:
                client.close()
            except BackendError as error:
                cleanup_error = str(error)
        summary = summarize(records)
        summary["mqtt_messages"] = dict(replies.counts)
        summary["publish_ack_ms"] = distribution([
            r["publish_ack_ms"] for r in records
            if r["phase"] == "measured" and r["status"] == "success" and r["publish_ack_ms"] is not None
        ])
        if cleanup_error:
            summary["cleanup_error"] = cleanup_error
        plan = self.describe()
        plan["resolved_endpoint"] = getattr(client, "endpoint", None)
        return RunResult(
            evaluation="mqtt", twin_name=self.deployment.twin_name, run_id=run_id,
            started_at=started, finished_at=utc_text(clock.utcnow()),
            successful=summary["failed_samples"] == 0,
            plan=plan, summary=summary, measurements=records,
        )

    def _sample(self, client, replies, clock, run_id, sequence, phase, timestamp, value):
        payload = {"iotDeviceId": self.target.device_id, "time": timestamp, self.options.property: value}
        with replies.lock:
            started = clock.monotonic()
            pending = _Pending(value, started, started + self.options.timeout_seconds)
            replies.active = pending  # Register before publish: an early reply is valid.
            if replies.failure:
                pending.status, pending.error = "connection_error", replies.failure
                pending.done.set()
        write_ms = 0.0
        if not pending.done.is_set():
            try:
                future = client.publish(self.deployment.resources.iot_topic, payload)
                write_ms = (clock.monotonic() - started) * 1000
                future.add_done_callback(lambda f: replies.acknowledged(pending, f))
            except BackendError as error:
                write_ms = (clock.monotonic() - started) * 1000
                with replies.lock:
                    if pending.status == "pending":
                        pending.status, pending.error = "write_error", str(error)
                        pending.done.set()
            pending.done.wait(timeout=max(0, pending.deadline - clock.monotonic()))
        with replies.lock:
            if pending.status == "pending":
                pending.status = "timeout"
                pending.error = "No matching processing reply arrived over MQTT before the deadline."
            end = pending.received_at if pending.received_at is not None else clock.monotonic()
            replies.finished[value] = pending.status
            replies.active = None
            return {
                "run_id": run_id, "sequence": sequence, "phase": phase,
                "target": self.target.path, "property": self.options.property,
                "device_id": self.target.device_id, "timestamp": timestamp,
                "value": value, "response_value": pending.response_value,
                "status": pending.status, "error": pending.error,
                "write_ms": write_ms, "read_ms": 0.0, "read_attempts": 0,
                "publish_ack_ms": pending.publish_ack_ms,
                "roundtrip_ms": (end - started) * 1000,
            }
