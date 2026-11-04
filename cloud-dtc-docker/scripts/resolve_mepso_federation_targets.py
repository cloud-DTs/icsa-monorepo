#!/usr/bin/env python3
"""Generate MEPSO federation Lambda sources with deployed target device IDs."""

from __future__ import annotations

import json
from pathlib import Path

from resolve_common import REPO_ROOT, find_device_id

LAMBDA_ROOT = REPO_ROOT / "demo-code" / "meps-demo"

TARGETS = {
    "__AGGREGATOR_TSO_INPUT_DEVICE_ID__": ("dtcAggreg", "requestedPower"),
    "__AGGREGATOR_DSO_INPUT_DEVICE_ID__": ("dtcAggreg", "ts1VoltageStatus"),
    "__AGGREGATOR_EC1_INPUT_DEVICE_ID__": ("dtcAggreg", "ec1BatteryStateOfCharge"),
    "__AGGREGATOR_EC2_INPUT_DEVICE_ID__": ("dtcAggreg", "ec2BatteryStateOfCharge"),
    "__AGGREGATOR_DECISION_DEVICE_ID__": ("dtcAggreg", "decisionVersion"),
    "__EC1_BATTERY_DEVICE_ID__": ("dtcEC1", "batteryPower"),
    "__EC1_DSR_DEVICE_ID__": ("dtcEC1", "dsrPower"),
    "__EC2_BATTERY_DEVICE_ID__": ("dtcEC2", "batteryPower"),
    "__EC2_DSR_DEVICE_ID__": ("dtcEC2", "dsrPower"),
}

COMPONENT_TARGETS = {
    "__DSO_TS1_DEVICE_ID__": ("dtcDSO", "ts1"),
    "__DSO_TS2_DEVICE_ID__": ("dtcDSO", "ts2"),
}


def find_component_device_id(twin: str, component: str) -> str:
    hierarchy_file = (
        REPO_ROOT
        / "pipeline"
        / "digital-twin-manager"
        / "deployments"
        / twin
        / "input"
        / "config_hierarchy.json"
    )
    hierarchy = json.loads(hierarchy_file.read_text(encoding="utf-8"))
    for entity in hierarchy:
        for child in entity.get("children", []):
            if child.get("type") == "component" and child.get("name") == component:
                return child["iotDeviceId"]
    raise SystemExit(f"No component '{component}' found in {hierarchy_file}.")


def render(template: Path, target: Path, replacements: dict[str, str]) -> None:
    source = template.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        source = source.replace(f'"{placeholder}"', f'"{value}"')
    unresolved = [
        placeholder
        for placeholder in (*TARGETS, *COMPONENT_TARGETS)
        if placeholder in source
    ]
    if unresolved:
        raise SystemExit(f"Unresolved placeholders in {template}: {unresolved}")
    target.write_text(source, encoding="utf-8")
    print(f"Generated {target.relative_to(REPO_ROOT)}")


def main() -> None:
    resolved = {
        placeholder: find_device_id(twin, prop)
        for placeholder, (twin, prop) in TARGETS.items()
    }
    resolved.update(
        {
            placeholder: find_component_device_id(twin, component)
            for placeholder, (twin, component) in COMPONENT_TARGETS.items()
        }
    )
    for directory in (
        "push-to-aggregator",
        "aggregator-decision",
        "dispatch-to-community",
    ):
        base = LAMBDA_ROOT / directory
        render(
            base / "lambda_function.py.template", base / "lambda_function.py", resolved
        )


if __name__ == "__main__":
    main()
