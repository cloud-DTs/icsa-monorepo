import deployment_state
import globals
from deployers.aws.iot.device_config import effective_iot_devices


def _devices_by_id(iot_devices):
  return {iot_device["id"]: iot_device for iot_device in iot_devices}


def previous_iot_devices():
  return effective_iot_devices(
    deployment_state.last_applied_config_iot_devices,
    deployment_state.last_applied_config_hierarchy,
  )


def desired_iot_devices():
  return effective_iot_devices(globals.config_iot_devices, globals.config_hierarchy)


def reconciled_iot_devices():
  previous_iot_device_configs = previous_iot_devices()
  desired_iot_device_configs = desired_iot_devices()

  previous_devices = _devices_by_id(previous_iot_device_configs)
  desired_devices = _devices_by_id(desired_iot_device_configs)

  device_ids = []
  for iot_device in previous_iot_device_configs:
    device_ids.append(iot_device["id"])

  for iot_device in desired_iot_device_configs:
    if iot_device["id"] not in previous_devices:
      device_ids.append(iot_device["id"])

  return [
    (previous_devices.get(iot_device_id), desired_devices.get(iot_device_id))
    for iot_device_id in device_ids
  ]
