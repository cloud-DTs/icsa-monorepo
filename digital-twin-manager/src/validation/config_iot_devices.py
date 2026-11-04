import re

from .common import (
  require_dict,
  require_keys,
  require_list,
  require_no_unknown_keys,
  require_string,
)
from .data_types import (
  SUPPORTED_DATA_TYPES,
  validate_data_type,
  validate_typed_value,
)


CONFIG_NAME = "config_iot_devices.json"

DEVICE_REQUIRED_KEYS = {
  "id",
  "properties",
}

DEVICE_OPTIONAL_KEYS = set()

PROPERTY_REQUIRED_KEYS = {
  "name",
  "dataType",
}

PROPERTY_OPTIONAL_KEYS = {
  "initValue",
}

IOT_DEVICE_ID_PATTERN = r"[A-Za-z0-9_-]+"
PROPERTY_NAME_PATTERN = r"[A-Za-z0-9_-]+"
RESERVED_PROPERTY_NAMES = {
  "iotDeviceId",
  "time",
}


def validate(config):
  require_list(config, CONFIG_NAME)

  seen_device_ids = set()

  for index, iot_device in enumerate(config):
    _validate_iot_device(iot_device, index, seen_device_ids)


def _validate_iot_device(iot_device, index, seen_device_ids):
  field = f"{CONFIG_NAME}[{index}]"

  require_dict(iot_device, field)
  require_keys(iot_device, DEVICE_REQUIRED_KEYS, field)
  require_no_unknown_keys(
    iot_device,
    DEVICE_REQUIRED_KEYS | DEVICE_OPTIONAL_KEYS,
    field,
  )

  _validate_iot_device_id(iot_device["id"], f"{field}.id", seen_device_ids)
  _validate_properties(iot_device["properties"], f"{field}.properties")


def _validate_iot_device_id(value, field, seen_device_ids):
  require_string(value, field)

  if not re.fullmatch(IOT_DEVICE_ID_PATTERN, value):
    raise ValueError(f"{field} must match regex: {IOT_DEVICE_ID_PATTERN}")

  if value in seen_device_ids:
    raise ValueError(f"{field} is duplicated: {value}")

  seen_device_ids.add(value)


def _validate_properties(properties, field):
  require_list(properties, field)

  seen_property_names = set()

  for index, iot_property in enumerate(properties):
    _validate_property(iot_property, f"{field}[{index}]", seen_property_names)


def _validate_property(iot_property, field, seen_property_names):
  require_dict(iot_property, field)
  require_keys(iot_property, PROPERTY_REQUIRED_KEYS, field)
  require_no_unknown_keys(
    iot_property,
    PROPERTY_REQUIRED_KEYS | PROPERTY_OPTIONAL_KEYS,
    field,
  )

  _validate_property_name(
    iot_property["name"],
    f"{field}.name",
    seen_property_names,
  )
  validate_data_type(iot_property["dataType"], f"{field}.dataType")

  if "initValue" in iot_property:
    validate_typed_value(
      iot_property["initValue"],
      iot_property["dataType"],
      f"{field}.initValue",
    )


def _validate_property_name(value, field, seen_property_names):
  require_string(value, field)

  if not re.fullmatch(PROPERTY_NAME_PATTERN, value):
    raise ValueError(f"{field} must match regex: {PROPERTY_NAME_PATTERN}")

  if value in RESERVED_PROPERTY_NAMES:
    raise ValueError(
      f"{field} must not use reserved property name: {value}"
    )

  if value in seen_property_names:
    raise ValueError(f"{field} is duplicated: {value}")

  seen_property_names.add(value)
