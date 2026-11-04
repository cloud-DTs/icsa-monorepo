import resource_names


TREE_NODE_TYPES = ("entity", "component")
COMPONENT_INSTANCE_KEYS = ("type", "name", "iotDeviceId", "componentTypeId", "children")


def _is_tree_node(entry):
  return entry.get("type") in TREE_NODE_TYPES


def _is_flat_iot_device(entry):
  return "id" in entry and not _is_tree_node(entry)


def _iot_device_from_component(component):
  iot_device = {
    key: value
    for key, value in component.items()
    if key not in COMPONENT_INSTANCE_KEYS
  }
  iot_device["id"] = component["iotDeviceId"]

  if "componentTypeId" in component:
    iot_device["componentTypeId"] = component["componentTypeId"]

  iot_device.setdefault("properties", [])
  return iot_device


def _add_iot_device(iot_devices, iot_devices_by_id, iot_device):
  iot_device_id = iot_device["id"]
  existing_iot_device = iot_devices_by_id.get(iot_device_id)

  if existing_iot_device is not None:
    if existing_iot_device != iot_device:
      raise ValueError(f"Duplicate IoT device id with different config: {iot_device_id}")

    return

  iot_devices_by_id[iot_device_id] = iot_device
  iot_devices.append(iot_device)


def _collect_iot_devices(entry, iot_devices, iot_devices_by_id):
  if isinstance(entry, list):
    for child in entry:
      _collect_iot_devices(child, iot_devices, iot_devices_by_id)
    return

  if not isinstance(entry, dict):
    return

  if _is_flat_iot_device(entry):
    _add_iot_device(iot_devices, iot_devices_by_id, dict(entry))
    return

  if entry.get("type") == "component" and entry.get("iotDeviceId") is not None:
    _add_iot_device(
      iot_devices,
      iot_devices_by_id,
      _iot_device_from_component(entry),
    )

  _collect_iot_devices(entry.get("children", []), iot_devices, iot_devices_by_id)


def _component_type_ids_from_hierarchy(config_hierarchy):
  component_type_ids_by_device_id = {}

  def _walk(entry):
    if isinstance(entry, list):
      for child in entry:
        _walk(child)
      return

    if not isinstance(entry, dict):
      return

    if (
      entry.get("type") == "component"
      and "iotDeviceId" in entry
      and "componentTypeId" in entry
    ):
      component_type_ids_by_device_id[entry["iotDeviceId"]] = entry["componentTypeId"]

    _walk(entry.get("children", []))

  _walk(config_hierarchy)
  return component_type_ids_by_device_id


def effective_iot_devices(config_iot_devices, config_hierarchy=None):
  iot_devices = []
  iot_devices_by_id = {}
  _collect_iot_devices(config_iot_devices, iot_devices, iot_devices_by_id)

  if config_hierarchy:
    component_type_ids_by_device_id = _component_type_ids_from_hierarchy(config_hierarchy)

    for iot_device in iot_devices:
      component_type_id = component_type_ids_by_device_id.get(iot_device["id"])

      if component_type_id is not None:
        iot_device["componentTypeId"] = component_type_id

  return iot_devices


def iot_device_ids_by_component_type(config, config_iot_devices, config_hierarchy):
  device_ids = {}
  for iot_device in effective_iot_devices(config_iot_devices, config_hierarchy):
    component_type_id = resource_names.twinmaker_component_type_id(config, iot_device)
    device_ids.setdefault(component_type_id, set()).add(str(iot_device["id"]))
  return device_ids


def infer_iot_device_id(component_type_id, device_ids_by_type):
  device_ids = device_ids_by_type.get(component_type_id, set())
  if len(device_ids) > 1:
    raise ValueError(
      f"Component Type {component_type_id} is shared by multiple IoT devices. "
      "Set iotDeviceId on each hierarchy component."
    )
  return next(iter(device_ids), None)
