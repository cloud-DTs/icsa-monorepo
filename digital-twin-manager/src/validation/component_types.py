"""Validate shared Component Type schemas in the desired configuration."""

from deployers.aws.iot.device_config import effective_iot_devices
from twinmaker_schema import build_property_definitions
import resource_names


def validate(config, config_iot_devices, config_hierarchy):
  schemas = {}
  for iot_device in effective_iot_devices(config_iot_devices, config_hierarchy):
    component_type_id = resource_names.twinmaker_component_type_id(config, iot_device)
    properties = build_property_definitions(iot_device)
    reference_id, reference_properties = schemas.setdefault(
      component_type_id, (iot_device["id"], properties),
    )
    if properties != reference_properties:
      raise ValueError(
        "IoT devices sharing TwinMaker Component Type "
        f"{component_type_id} have different properties: "
        f"{reference_id} vs {iot_device['id']}"
      )
