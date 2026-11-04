from __future__ import annotations

import csv
from dataclasses import asdict
import json
from pathlib import Path
import platform
import re
from importlib.metadata import version

from . import __version__
from .contracts import RunResult


def write_report(result: RunResult, output: Path) -> Path:
    for field, value in (("twin_name", result.twin_name), ("run_id", result.run_id)):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError(f"Invalid report {field}.")
    directory = Path(output) / result.twin_name / result.run_id
    directory.mkdir(parents=True, exist_ok=False)
    fields = list(dict.fromkeys(key for record in result.measurements for key in record))
    with (directory / "measurements.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in result.measurements:
            writer.writerow({key: _csv_value(key, value) for key, value in record.items()})
    document = asdict(result)
    document.pop("measurements")
    document.update(schema_version=1, service_version=__version__, measurements_file="measurements.csv")
    document["runtime"] = {"python": platform.python_version(), "boto3": version("boto3")}
    # Write the completion document last so its presence means both files exist.
    (directory / "summary.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return directory


def _csv_value(key, value):
    if key == "value" or isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
