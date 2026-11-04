"""Shared resolve-and-inject logic for the fed-sysml device-ID enablement scripts.

Several federation-owned push Strategy Lambdas need one thing fed-sysml
cannot express: the literal target device ID for the property they write
into. These IDs are only known after the target twin has been deployed, so
each one is resolved from that twin's deployed config_iot_devices.json and
baked into the Lambda source as a plain Python string constant.

The Lambda source for each of these federations lives as TWO files:

  <name>/lambda_function.py.template  - git-tracked, always keeps the
      placeholder, never modified by this module.
  <name>/lambda_function.py           - the file fed-sysml/Docker actually
      reads (demo-code/ is bind-mounted as /pipeline/code); regenerated from
      the template on every run and gitignored, so a resolved copy from a
      previous deployment is never committed and never silently reused.

Regenerating from the immutable template on every run - instead of mutating
one file in place - means a redeploy that changes the device ID is always
picked up. There is no "the placeholder was already replaced" dead end.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def find_device_id(twin_name: str, property_name: str) -> str:
    """Resolve a device ID from a twin's deployed config_iot_devices.json."""
    devices_file = (
        REPO_ROOT / "pipeline" / "digital-twin-manager" / "deployments"
        / twin_name / "input" / "config_iot_devices.json"
    )
    if not devices_file.is_file():
        raise SystemExit(
            f"Missing deployed device list: {devices_file}. "
            f"Deploy '{twin_name}' before running federation."
        )

    devices = json.loads(devices_file.read_text(encoding="utf-8"))
    for device in devices:
        for prop in device.get("properties", []):
            if prop.get("name") == property_name:
                return device["id"]

    raise SystemExit(
        f"No device with property '{property_name}' found in {devices_file}."
    )


def resolve_and_inject(
    *,
    source_twin: str,
    property_name: str,
    placeholder: str,
    template_file: Path,
    target_file: Path,
    label: str,
) -> None:
    """Resolve `property_name`'s device ID on `source_twin` and (re)generate
    `target_file` from `template_file` with the placeholder replaced.

    `template_file` is read-only here and must always contain the
    placeholder; `target_file` is fully overwritten on every call, so it can
    never end up stuck on a stale ID from an earlier deployment.
    """
    if not template_file.is_file():
        raise SystemExit(f"Missing Lambda source template: {template_file}")

    device_id = find_device_id(source_twin, property_name)

    template_code = template_file.read_text(encoding="utf-8")
    if f'"{placeholder}"' not in template_code:
        raise SystemExit(
            f"Placeholder '{placeholder}' not found in {template_file}. "
            "The template must always contain it verbatim - if this file was "
            "hand-edited to a resolved device ID, restore the placeholder; "
            f"{target_file.name} is regenerated from the template, not the "
            "other way around."
        )

    resolved_code = template_code.replace(f'"{placeholder}"', f'"{device_id}"')
    target_file.write_text(resolved_code, encoding="utf-8")
    print(f"Injected {label} '{device_id}' into {target_file}")
