"""Resolve device bindings using the Cloud Deployer configuration rules."""


def walk_tree(entry):
    if isinstance(entry, list):
        for child in entry:
            yield from walk_tree(child)
    elif isinstance(entry, dict):
        yield entry
        yield from walk_tree(entry.get("children", []))


class DeviceRegistry:
    def __init__(self, twin_name: str, device_config, hierarchy):
        self.twin_name = twin_name
        self.devices: dict[str, dict] = {}
        self.device_ids_by_type: dict[str, set[str]] = {}

        for entry in walk_tree(device_config):
            if entry.get("type") not in ("entity", "component") and "id" in entry:
                device = dict(entry)
            elif entry.get("type") == "component" and entry.get("iotDeviceId") is not None:
                instance_keys = {"type", "name", "iotDeviceId", "children"}
                device = {key: value for key, value in entry.items() if key not in instance_keys}
                device["id"] = entry["iotDeviceId"]
                device.setdefault("properties", [])
            else:
                continue

            device_id = device["id"]
            if device_id in self.devices and self.devices[device_id] != device:
                raise ValueError(f"Duplicate IoT device id with different config: {device_id}")
            self.devices[device_id] = device

        # Process every root before resolving type-only references in any entity.
        for entry in walk_tree(hierarchy):
            if entry.get("type") == "component" and "iotDeviceId" in entry and "componentTypeId" in entry:
                device = self.devices.get(entry["iotDeviceId"])
                if device is not None:
                    device["componentTypeId"] = entry["componentTypeId"]

        schemas = {}
        for device_id, device in self.devices.items():
            type_id = f"{twin_name}-{device.get('componentTypeId') or device_id}"
            self.device_ids_by_type.setdefault(type_id, set()).add(device_id)
            schema = {}
            for prop in device.get("properties", []):
                name = prop["name"]
                if name in ("iotDeviceId", "time"):
                    raise ValueError(f"Property {name} is reserved for telemetry routing")
                if name in schema:
                    raise ValueError(f"Duplicate property {name} on device {device_id}")
                schema[name] = prop["dataType"]
            reference_id, reference_schema = schemas.setdefault(type_id, (device_id, schema))
            if schema != reference_schema:
                raise ValueError(
                    f"IoT devices sharing Component Type {type_id} have different properties: "
                    f"{reference_id} vs {device_id}"
                )

    def resolve(self, component: dict) -> tuple[str | None, str]:
        if "iotDeviceId" in component:
            device_id = component["iotDeviceId"]
            if device_id not in self.devices:
                raise ValueError(f"Component {component['name']} references unknown IoT device: {device_id}")
            # With a device ID, componentTypeId is always a logical name.
            logical_type_id = component.get("componentTypeId", device_id)
            return device_id, f"{self.twin_name}-{logical_type_id}"

        if "componentTypeId" not in component:
            raise ValueError(f"Component {component['name']} needs iotDeviceId or componentTypeId.")
        # Without a device ID, componentTypeId is the full AWS ID, including its prefix.
        type_id = component["componentTypeId"]
        device_ids = self.device_ids_by_type.get(type_id, set())
        if len(device_ids) > 1:
            raise ValueError(f"Component Type {type_id} is shared by multiple devices. Set iotDeviceId.")
        return next(iter(device_ids), None), type_id
