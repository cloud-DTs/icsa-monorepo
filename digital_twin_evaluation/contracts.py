from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Protocol


type Json = None | bool | int | float | str | list[Json] | dict[str, Json]


@dataclass(frozen=True)
class Property:
    name: str
    data_type: str


@dataclass(frozen=True)
class Target:
    path: str
    entity_id: str
    component_name: str
    device_id: str
    properties: tuple[Property, ...]

    def property_type(self, name: str) -> str:
        for prop in self.properties:
            if prop.name == name:
                return prop.data_type
        raise ValueError(f"Unknown property '{name}' on target '{self.path}'.")


@dataclass(frozen=True)
class Resources:
    writer_function: str
    reader_function: str
    workspace_id: str
    iot_topic: str


@dataclass(frozen=True)
class Deployment:
    twin_name: str
    region: str
    resources: Resources
    targets: tuple[Target, ...]
    fingerprint: str
    applied_at: str
    state_directory: Path | None = None

    def target(self, path: str) -> Target:
        for target in self.targets:
            if target.path == path:
                return target
        available = ", ".join(target.path for target in self.targets)
        raise ValueError(f"Unknown target '{path}'. Available targets: {available}")


@dataclass(frozen=True)
class Reading:
    timestamp: str
    value: Json


class BackendError(RuntimeError):
    """An AWS call or response failed; the sample must not count as successful."""


class TelemetryBackend(Protocol):
    def write(self, mode: str, payload: dict[str, Json]) -> None: ...

    def read(
        self, target: Target, property_name: str, data_type: str, timestamp: str
    ) -> list[Reading]: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def utcnow(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    monotonic = staticmethod(time.perf_counter)
    sleep = staticmethod(time.sleep)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(timezone.utc)


def utc_text(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class RunResult:
    evaluation: str
    twin_name: str
    run_id: str
    started_at: str
    finished_at: str
    successful: bool
    plan: dict[str, Json]
    summary: dict[str, Json]
    measurements: list[dict[str, Json]]


class PreparedEvaluation(Protocol):
    def describe(self) -> dict[str, Json]: ...

    def run(self) -> RunResult: ...


class Evaluation(Protocol):
    def prepare(
        self, deployment: Deployment, parameters: dict[str, Json]
    ) -> PreparedEvaluation: ...
