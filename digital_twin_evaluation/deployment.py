from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .contracts import Deployment, Property, Resources, Target


STATE_DIRECTORY = ".digital-twin-manager-state"
PROPERTY_TYPES = {
    "INTEGER", "DOUBLE", "STRING", "VECTOR_INTEGER", "VECTOR_DOUBLE", "VECTOR_STRING",
}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read JSON file '{path}': {error}") from error


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value


def load_deployment(source: Path) -> Deployment:
    source = Path(source).resolve()
    candidates = (source, source / STATE_DIRECTORY, source / "output" / STATE_DIRECTORY)
    state = next((path for path in candidates if (path / "metadata.json").is_file()), None)
    if state is None:
        raise ValueError(f"No applied state found under '{source}'. Complete deploy or init-state first.")

    metadata = read_json(state / "metadata.json")
    if not isinstance(metadata, dict):
        raise ValueError("Applied state metadata must be an object.")
    if type(metadata.get("stateVersion")) is not int or metadata["stateVersion"] != 1:
        raise ValueError("Unsupported applied stateVersion; expected version 1.")

    documents = {
        name: read_json(state / "configs" / name)
        for name in ("config.json", "config_hierarchy.json", "config_iot_devices.json")
    }
    config = documents["config.json"]
    if not isinstance(config, dict):
        raise ValueError("Applied config.json must be an object.")
    twin = require_text(config.get("digital_twin_name"), "Applied twin name")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,10}", twin):
        raise ValueError("Applied twin name does not match the manager version 1 naming contract.")
    if metadata.get("digitalTwinName") != twin:
        raise ValueError("Applied metadata and config belong to different twins.")
    region = require_text(metadata.get("awsRegion"), "AWS region")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d+", region):
        raise ValueError("Invalid AWS region in applied state.")

    devices = _devices(documents["config_iot_devices.json"])
    targets = _targets(documents["config_hierarchy.json"], devices)
    fingerprint = hashlib.sha256(json.dumps(
        {"metadata": metadata, "configs": documents},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return Deployment(
        twin_name=twin,
        region=region,
        resources=Resources(
            writer_function=f"{twin}-persister",
            reader_function=f"{twin}-hot-reader",
            workspace_id=f"{twin}-twinmaker",
            iot_topic=f"{twin}/iot-data",
        ),
        targets=tuple(targets),
        fingerprint=fingerprint,
        applied_at=require_text(metadata.get("updatedAt"), "Applied state updatedAt"),
        state_directory=state,
    )


def _devices(raw: object) -> dict[str, tuple[Property, ...]]:
    if not isinstance(raw, list):
        raise ValueError("Applied IoT device config must be a list.")
    devices = {}
    for device in raw:
        if not isinstance(device, dict):
            raise ValueError("Each applied device must be an object.")
        device_id = require_text(device.get("id"), "IoT device id")
        if device_id in devices:
            raise ValueError(f"Duplicate device id: {device_id}")
        properties = device.get("properties")
        if not isinstance(properties, list):
            raise ValueError(f"Properties of device '{device_id}' must be a list.")
        parsed = []
        names = set()
        for prop in properties:
            if not isinstance(prop, dict):
                raise ValueError("Each device property must be an object.")
            name = require_text(prop.get("name"), "Property name")
            data_type = prop.get("dataType")
            if name in names or not isinstance(data_type, str) or data_type not in PROPERTY_TYPES:
                raise ValueError(f"Duplicate property or unsupported data type on '{device_id}.{name}'.")
            names.add(name)
            parsed.append(Property(name, data_type))
        devices[device_id] = tuple(parsed)
    return devices


def _targets(raw: object, devices: dict[str, tuple[Property, ...]]) -> list[Target]:
    if not isinstance(raw, list):
        raise ValueError("Applied hierarchy must be a list.")
    targets = []
    seen = set()

    def visit(nodes: list, parent_path: tuple[str, ...], entity_id: str | None):
        for node in nodes:
            if not isinstance(node, dict):
                raise ValueError("Each hierarchy node must be an object.")
            name = require_text(node.get("name"), "Hierarchy name")
            path = (*parent_path, name)
            if node.get("type") == "entity":
                children = node.get("children", [])
                if not isinstance(children, list):
                    raise ValueError("Entity children must be a list.")
                visit(children, path, require_text(node.get("id"), "Entity id"))
            elif node.get("type") == "component":
                # External components have no managed device and cannot be write targets.
                if "iotDeviceId" not in node:
                    continue
                device_id = require_text(node["iotDeviceId"], "Component device id")
                if entity_id is None or device_id not in devices:
                    raise ValueError(f"Missing entity or unknown device for '{'.'.join(path)}'.")
                logical_path = ".".join(path)
                if logical_path in seen:
                    raise ValueError(f"Duplicate logical target: {logical_path}")
                seen.add(logical_path)
                targets.append(Target(logical_path, entity_id, name, device_id, devices[device_id]))
            else:
                raise ValueError(f"Unknown hierarchy node type on '{'.'.join(path)}'.")

    visit(raw, (), None)
    return targets
