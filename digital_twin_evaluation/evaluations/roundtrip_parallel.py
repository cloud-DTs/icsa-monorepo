"""Run bounded groups of roundtrip cycles through one shared backend."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import timedelta, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from ..contracts import Clock, Json, RunResult, SystemClock, TelemetryBackend, utc_text
from ..statistics import summarize

if TYPE_CHECKING:
    from .roundtrip import RoundtripPlan


def run_parallel(
    plans: tuple[RoundtripPlan, ...], description: dict[str, Json], *,
    backend: TelemetryBackend | None = None, clock: Clock | None = None,
) -> RunResult:
    first = plans[0]
    options = first.options
    workers = min(options.concurrency, max(options.samples, options.warmup) * len(plans))
    if backend is None:
        from ..aws import AwsTelemetryBackend
        backend = AwsTelemetryBackend(
            first.deployment, options.request_timeout_seconds,
            max_pool_connections=workers, mode=options.mode,
        )
    clock = clock or SystemClock()
    run_id = uuid4().hex
    started = utc_text(clock.utcnow())
    run_started = clock.monotonic()
    records = []
    previous = {}

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="roundtrip") as executor:
        def submit(plan, sequence, phase):
            # Allocate timestamps only on the scheduling thread. Repeated values
            # on the same device must still produce distinct database records.
            moment = clock.utcnow().astimezone(timezone.utc)
            moment = moment.replace(microsecond=moment.microsecond // 1000 * 1000)
            last = previous.get(plan.target.device_id)
            if last is not None and moment <= last:
                moment = last + timedelta(milliseconds=1)
            previous[plan.target.device_id] = moment
            return executor.submit(
                plan._sample, backend, clock, run_id, sequence, phase, utc_text(moment),
            )

        def run_phase(phase, count, offset):
            jobs = (
                (plan, offset + sample * len(plans) + index)
                for sample in range(count)
                for index, plan in enumerate(plans)
            )
            pending = set()
            for _ in range(workers):
                job = next(jobs, None)
                if job is None:
                    break
                pending.add(submit(*job, phase))
            while pending:
                completed, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    records.append(future.result())
                    job = next(jobs, None)
                    if job is not None:
                        pending.add(submit(*job, phase))

        run_phase("warmup", options.warmup, 0)
        measured_started = clock.monotonic()
        run_phase("measured", options.samples, options.warmup * len(plans))
        measured_seconds = clock.monotonic() - measured_started

    duration_ms = (clock.monotonic() - run_started) * 1000
    records.sort(key=lambda record: record["sequence"])
    summary = summarize(records)
    summary.update(
        duration_ms=duration_ms,
        measured_duration_ms=measured_seconds * 1000,
        successful_samples_per_second=(
            summary["successful_samples"] / measured_seconds if measured_seconds > 0 else None
        ),
    )
    if "targets" in description:
        grouped = {plan.target.device_id: [] for plan in plans}
        for record in records:
            grouped[record["device_id"]].append(record)
        targets = [{
            "target": plan.target.path, "device_id": plan.target.device_id,
            "property": plan.options.property, **summarize(grouped[plan.target.device_id]),
        } for plan in plans]
        summary.update(target_count=len(targets), targets=targets)
    return RunResult(
        evaluation="roundtrip", twin_name=first.deployment.twin_name,
        run_id=run_id, started_at=started, finished_at=utc_text(clock.utcnow()),
        successful=summary["failed_samples"] == 0,
        plan=description, summary=summary, measurements=records,
    )
