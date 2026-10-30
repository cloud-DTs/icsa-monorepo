import math

from .contracts import Json


def distribution(values: list[float]) -> dict[str, Json]:
    ordered = sorted(values)
    result = {name: None for name in ("min", "p50", "p95", "p99", "max")}
    if ordered:
        result.update({
            "min": ordered[0],
            "p50": ordered[math.ceil(0.50 * len(ordered)) - 1],
            "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
            "p99": ordered[math.ceil(0.99 * len(ordered)) - 1],
            "max": ordered[-1],
        })
    return result


def summarize(records: list[dict[str, Json]]) -> dict[str, Json]:
    measured = [record for record in records if record["phase"] == "measured"]
    successful = [record for record in measured if record["status"] == "success"]
    warmup = [record for record in records if record["phase"] == "warmup"]
    statuses = {}
    for record in measured:
        status = record["status"]
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "measured_samples": len(measured),
        "successful_samples": len(successful),
        "failed_samples": len(measured) - len(successful),
        "warmup_samples": len(warmup),
        "warmup_failed": sum(record["status"] != "success" for record in warmup),
        "success_rate": len(successful) / len(measured) if measured else 0.0,
        "statuses": statuses,
        "percentile_method": "nearest_rank",
        "latencies_ms": {
            name: distribution([record[key] for record in successful])
            for name, key in (("write", "write_ms"), ("read", "read_ms"), ("roundtrip", "roundtrip_ms"))
        },
    }
