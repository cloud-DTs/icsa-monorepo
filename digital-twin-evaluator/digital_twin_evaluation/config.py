from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from .contracts import Json
from .deployment import read_json, require_text


@dataclass(frozen=True)
class EvaluationConfig:
    evaluation: str
    parameters: dict[str, Json]


def load_config(path: Path) -> EvaluationConfig:
    raw = read_json(path)
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "evaluation", "parameters"}:
        raise ValueError("Evaluation config requires schema_version, evaluation and parameters only.")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("Unsupported evaluation schema_version; expected 1.")
    name = require_text(raw["evaluation"], "evaluation")
    if not isinstance(raw["parameters"], dict):
        raise ValueError("Evaluation parameters must be an object.")
    return EvaluationConfig(name, raw["parameters"])


def integer(value: object, field: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}.")
    return value


def positive_number(value: object, field: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be a finite number > 0.")
    return float(value)


def valid_value(value: Json, data_type: str) -> bool:
    if data_type == "STRING":
        return isinstance(value, str)
    if data_type == "INTEGER":
        return type(value) is int
    if data_type == "DOUBLE":
        return type(value) in (int, float) and math.isfinite(value)
    if data_type.startswith("VECTOR_"):
        return isinstance(value, list) and all(valid_value(item, data_type[7:]) for item in value)
    return False
