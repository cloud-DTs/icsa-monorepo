"""Validate a processing reply path without changing deployed resources."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

from ..config import integer, positive_number
from ..contracts import Deployment, Json, Target
from ..deployment import read_json, require_text


def topic_name(value: object) -> str:
    topic = require_text(value, "response_topic")
    if any(char in topic for char in ("+", "#", "\x00")) or len(topic.encode("utf-8")) > 256:
        raise ValueError("response_topic must be an exact MQTT topic without wildcards.")
    return topic


@dataclass(frozen=True)
class MqttOptions:
    property: str
    value_range: tuple[float, float]
    response_topic: str
    response_value_path: tuple[str, ...]
    response_match: dict[str, Json]
    feedback_action: str | None
    feedback_fingerprint: str | None
    endpoint: str | None
    samples: int
    warmup: int
    timeout_seconds: float
    setup_timeout_seconds: float


def resolve_options(deployment: Deployment, parameters: dict[str, Json]) -> tuple[Target, MqttOptions]:
    allowed = {
        "target", "property", "value_range", "feedback_action", "response_topic",
        "response_value_path", "response_match", "endpoint", "samples", "warmup",
        "timeout_seconds", "setup_timeout_seconds", "concurrency",
    }
    if unknown := set(parameters) - allowed:
        raise ValueError(f"Unknown MQTT parameters: {', '.join(sorted(unknown))}")
    if integer(parameters.get("concurrency", 1), "concurrency", 1) != 1:
        raise ValueError("MQTT value correlation requires concurrency 1: deployed actions can read latest state.")
    target = deployment.target(require_text(parameters.get("target"), "target"))
    prop = require_text(parameters.get("property"), "property")
    if prop in ("iotDeviceId", "time") or target.property_type(prop) != "DOUBLE":
        raise ValueError("MQTT value correlation requires a deployed DOUBLE telemetry property.")
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
    path = parameters.get("response_value_path")
    if not isinstance(path, list) or not 1 <= len(path) <= 16 or any(not isinstance(k, str) or not k for k in path):
        raise ValueError("response_value_path must be a list of 1 to 16 non-empty object keys.")
    match = parameters.get("response_match", {})
    if not isinstance(match, dict):
        raise ValueError("response_match must be an object of expected top-level response fields.")
    try:
        json.dumps(match, allow_nan=False)
    except (ValueError, TypeError) as error:
        raise ValueError("response_match must contain finite JSON values.") from error
    endpoint = parameters.get("endpoint")
    if endpoint is not None and (
        not isinstance(endpoint, str) or len(endpoint) > 253
        or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", endpoint)
    ):
        raise ValueError("endpoint must be a host name without a URL scheme, port, or path.")
    action = parameters.get("feedback_action")
    fingerprint = None
    if action is not None:
        action = require_text(action, "feedback_action")
        if "response_topic" in parameters:
            raise ValueError("Use feedback_action or response_topic, not both.")
        reply_topic, fingerprint = _applied_feedback(deployment, target, prop, action)
    else:
        reply_topic = topic_name(parameters.get("response_topic"))
    if reply_topic == deployment.resources.iot_topic:
        raise ValueError("response_topic must differ from the publish topic; a broker echo does not prove processing.")
    return target, MqttOptions(
        property=prop, value_range=(lower, upper), response_topic=reply_topic,
        response_value_path=tuple(path), response_match=match,
        feedback_action=action, feedback_fingerprint=fingerprint, endpoint=endpoint,
        samples=integer(parameters.get("samples", 100), "samples", 1),
        warmup=integer(parameters.get("warmup", 10), "warmup", 0),
        timeout_seconds=positive_number(parameters.get("timeout_seconds", 10), "timeout_seconds"),
        setup_timeout_seconds=positive_number(parameters.get("setup_timeout_seconds", 10), "setup_timeout_seconds"),
    )


def _applied_feedback(deployment, target, prop, action_name):
    if deployment.state_directory is None:
        raise ValueError("Applied state directory is required to resolve feedback_action.")
    events = read_json(deployment.state_directory / "configs/config_events.json")
    if not isinstance(events, list):
        raise ValueError("Applied config_events.json must be a list.")
    matches = [e for e in events if isinstance(e, dict) and isinstance(e.get("action"), dict)
               and e["action"].get("functionName") == action_name]
    if len(matches) != 1:
        raise ValueError(f"Expected one applied feedback action '{action_name}', found {len(matches)}.")
    event = matches[0]
    action = event["action"]
    feedback = action.get("feedback")
    if action.get("type") != "lambda" or not isinstance(feedback, dict) or feedback.get("type") != "mqtt":
        raise ValueError("Selected action has no applied MQTT feedback route.")
    if feedback.get("payload") != "action-result":
        raise ValueError("Selected feedback must publish action-result, not a constant payload.")
    binding = f"{target.entity_id}.{target.component_name}.{prop}"
    inputs = action.get("inputParameters", [])
    if not isinstance(inputs, list) or not any(isinstance(p, dict) and p.get("id") == binding for p in inputs):
        raise ValueError("Selected action does not consume the selected telemetry property.")
    condition = event.get("condition")
    if not isinstance(condition, str) or binding not in condition.split():
        raise ValueError("Selected telemetry property does not trigger the applied action condition.")
    topic = feedback.get("topic")
    if not topic:
        device = require_text(feedback.get("iotDeviceId"), "Feedback device id")
        # Same topic contract as manager-state-v1 event-feedback.
        topic = f"{deployment.twin_name}-{device}"
    fingerprint = hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest()
    return topic_name(topic), fingerprint
