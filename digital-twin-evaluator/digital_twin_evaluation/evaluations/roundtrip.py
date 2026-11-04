from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta, timezone
from uuid import uuid4

from ..config import integer, positive_number, valid_value
from ..contracts import (
    BackendError, Clock, Deployment, Json, RunResult, SystemClock, Target, TelemetryBackend,
    utc_text as _utc_text,
)
from ..deployment import require_text
from ..statistics import summarize
from .roundtrip_parallel import run_parallel


@dataclass(frozen=True)
class RoundtripOptions:
    mode: str
    property: str
    value: Json
    samples: int
    warmup: int
    timeout_seconds: float
    poll_interval_seconds: float
    request_timeout_seconds: float
    concurrency: int = 1


class RoundtripEvaluation:
    def prepare(
        self, deployment: Deployment, parameters: dict[str, Json]
    ) -> RoundtripPlan | RoundtripTargetsPlan:
        if "targets" in parameters:
            return self._prepare_targets(deployment, parameters)
        return self._prepare_single(deployment, parameters)

    def _prepare_single(self, deployment: Deployment, parameters: dict[str, Json]) -> RoundtripPlan:
        allowed = {
            "mode", "target", "property", "value", "samples", "warmup",
            "timeout_seconds", "poll_interval_seconds", "request_timeout_seconds",
            "concurrency",
        }
        unknown = set(parameters) - allowed
        if unknown:
            raise ValueError(f"Unknown roundtrip parameters: {', '.join(sorted(unknown))}")
        target = deployment.target(require_text(parameters.get("target"), "target"))
        prop = require_text(parameters.get("property"), "property")
        if prop in ("iotDeviceId", "time"):
            raise ValueError("The evaluation property must not replace telemetry routing fields.")
        data_type = target.property_type(prop)
        if "value" not in parameters or not valid_value(parameters["value"], data_type):
            raise ValueError(f"value must match the deployed property type {data_type}.")
        mode = parameters.get("mode", "storage")
        if mode not in ("storage", "ingestion"):
            raise ValueError("mode must be storage or ingestion.")
        options = RoundtripOptions(
            mode=mode, property=prop, value=parameters["value"],
            samples=integer(parameters.get("samples", 100), "samples", 1),
            warmup=integer(parameters.get("warmup", 10), "warmup", 0),
            timeout_seconds=positive_number(parameters.get("timeout_seconds", 10), "timeout_seconds"),
            poll_interval_seconds=positive_number(parameters.get("poll_interval_seconds", 0.05), "poll_interval_seconds"),
            request_timeout_seconds=positive_number(parameters.get("request_timeout_seconds", 10), "request_timeout_seconds"),
            concurrency=integer(parameters.get("concurrency", 1), "concurrency", 1),
        )
        return RoundtripPlan(deployment, target, data_type, options)

    def _prepare_targets(self, deployment: Deployment, parameters: dict[str, Json]) -> RoundtripTargetsPlan:
        if set(parameters).intersection({"target", "property", "value"}):
            raise ValueError("Use targets or a single target/property/value, not both.")
        entries = parameters["targets"]
        if not isinstance(entries, list) or not entries:
            raise ValueError("targets must be a non-empty list.")
        common = {key: value for key, value in parameters.items() if key != "targets"}
        plans = []
        devices = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"target", "property", "value"}:
                raise ValueError("Each targets entry requires target, property and value only.")
            plan = self._prepare_single(deployment, {**common, **entry})
            if plan.target.device_id in devices:
                raise ValueError(f"Device appears more than once in targets: {plan.target.device_id}")
            devices.add(plan.target.device_id)
            plans.append(plan)
        return RoundtripTargetsPlan(tuple(plans))


@dataclass(frozen=True)
class RoundtripPlan:
    deployment: Deployment
    target: Target
    data_type: str
    options: RoundtripOptions

    def describe(self) -> dict[str, Json]:
        return {
            "schema_version": 1,
            "evaluation": "roundtrip",
            "twin_name": self.deployment.twin_name,
            "region": self.deployment.region,
            "source": {
                "adapter": "manager-state-v1",
                "fingerprint": self.deployment.fingerprint,
                "applied_at": self.deployment.applied_at,
            },
            "resources": asdict(self.deployment.resources),
            "target": {
                "path": self.target.path, "entity_id": self.target.entity_id,
                "component_name": self.target.component_name, "device_id": self.target.device_id,
                "property": self.options.property, "data_type": self.data_type,
            },
            "parameters": asdict(self.options),
            "execution": "parallel" if self.options.concurrency > 1 else "sequential",
            "latency_scope": "per message, immediately before send through verified read; excludes worker queue wait",
            "timeout_scope": "whole_cycle; an in-flight SDK call can exceed the deadline",
            "read_consistency": "deployed reader default; no consistency settings are changed",
            "cold_start_detection": "not collected; warmup does not prove absence of cold starts",
        }

    def run(
        self, *, backend: TelemetryBackend | None = None, clock: Clock | None = None
    ) -> RunResult:
        if self.options.concurrency > 1:
            return run_parallel((self,), self.describe(), backend=backend, clock=clock)
        if backend is None:
            from ..aws import AwsTelemetryBackend
            backend = AwsTelemetryBackend(
                self.deployment, self.options.request_timeout_seconds, mode=self.options.mode,
            )
        clock = clock or SystemClock()
        run_id = uuid4().hex
        started = _utc_text(clock.utcnow())
        records = []
        previous_timestamp = None
        for sequence in range(self.options.warmup + self.options.samples):
            moment = clock.utcnow().astimezone(timezone.utc)
            moment = moment.replace(microsecond=moment.microsecond // 1000 * 1000)
            if previous_timestamp is not None and moment <= previous_timestamp:
                moment = previous_timestamp + timedelta(milliseconds=1)
            previous_timestamp = moment
            timestamp = _utc_text(moment)
            phase = "warmup" if sequence < self.options.warmup else "measured"
            records.append(self._sample(backend, clock, run_id, sequence, phase, timestamp))
        summary = summarize(records)
        return RunResult(
            evaluation="roundtrip", twin_name=self.deployment.twin_name,
            run_id=run_id, started_at=started,
            finished_at=_utc_text(clock.utcnow()), successful=summary["failed_samples"] == 0,
            plan=self.describe(), summary=summary, measurements=records,
        )

    def _sample(self, backend, clock, run_id, sequence, phase, timestamp):
        payload = {
            "iotDeviceId": self.target.device_id,
            "time": timestamp,
            self.options.property: self.options.value,
        }
        started = clock.monotonic()
        deadline = started + self.options.timeout_seconds
        record = {
            "run_id": run_id, "sequence": sequence, "phase": phase,
            "target": self.target.path, "property": self.options.property,
            "device_id": self.target.device_id, "timestamp": timestamp,
            "value": self.options.value, "status": "timeout", "error": "",
            "write_ms": 0.0, "read_ms": 0.0, "roundtrip_ms": 0.0,
            "read_attempts": 0,
        }
        try:
            backend.write(self.options.mode, payload)
        except BackendError as error:
            record.update(status="write_error", error=str(error))
            record["write_ms"] = (clock.monotonic() - started) * 1000
        else:
            record["write_ms"] = (clock.monotonic() - started) * 1000
            while clock.monotonic() < deadline:
                read_started = clock.monotonic()
                record["read_attempts"] += 1
                try:
                    readings = backend.read(self.target, self.options.property, self.data_type, timestamp)
                except BackendError as error:
                    record.update(status="read_error", error=str(error))
                    record["read_ms"] += (clock.monotonic() - read_started) * 1000
                    break
                record["read_ms"] += (clock.monotonic() - read_started) * 1000
                if clock.monotonic() > deadline:
                    break
                if any(
                    reading.timestamp == timestamp
                    and valid_value(reading.value, self.data_type)
                    and reading.value == self.options.value
                    for reading in readings
                ):
                    record["status"] = "success"
                    break
                remaining = deadline - clock.monotonic()
                if remaining > 0:
                    clock.sleep(min(self.options.poll_interval_seconds, remaining))
        record["roundtrip_ms"] = (clock.monotonic() - started) * 1000
        if record["status"] == "timeout":
            record["error"] = "The matching record was not returned before the roundtrip deadline."
        return record


@dataclass(frozen=True)
class RoundtripTargetsPlan:
    plans: tuple[RoundtripPlan, ...]

    def describe(self) -> dict[str, Json]:
        description = self.plans[0].describe()
        description.pop("target")
        common = asdict(self.plans[0].options)
        common.pop("property")
        common.pop("value")
        description["parameters"] = common
        description["targets"] = [
            {**plan.describe()["target"], "value": plan.options.value}
            for plan in self.plans
        ]
        description["execution"] = "parallel" if self.plans[0].options.concurrency > 1 else "sequential"
        return description

    def run(
        self, *, backend: TelemetryBackend | None = None, clock: Clock | None = None
    ) -> RunResult:
        first = self.plans[0]
        if first.options.concurrency > 1:
            return run_parallel(self.plans, self.describe(), backend=backend, clock=clock)
        if backend is None:
            from ..aws import AwsTelemetryBackend
            backend = AwsTelemetryBackend(
                first.deployment, first.options.request_timeout_seconds, mode=first.options.mode,
            )
        clock = clock or SystemClock()
        run_id = uuid4().hex
        started = _utc_text(clock.utcnow())
        records = []
        targets = []
        for plan in self.plans:
            result = plan.run(backend=backend, clock=clock)
            for record in result.measurements:
                records.append({**record, "run_id": run_id, "sequence": len(records)})
            targets.append({
                "target": plan.target.path, "device_id": plan.target.device_id,
                "property": plan.options.property, **result.summary,
            })
        summary = summarize(records)
        summary.update(target_count=len(targets), targets=targets)
        return RunResult(
            evaluation="roundtrip", twin_name=first.deployment.twin_name,
            run_id=run_id, started_at=started, finished_at=_utc_text(clock.utcnow()),
            successful=summary["failed_samples"] == 0,
            plan=self.describe(), summary=summary, measurements=records,
        )
