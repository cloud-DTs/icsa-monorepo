import re

from .common import (
  keys_text,
  require_dict,
  require_keys,
  require_list,
  require_no_unknown_keys,
  require_string,
)


CONFIG_NAME = "config_hierarchy.json"

ENTITY_TYPE = "entity"
COMPONENT_TYPE = "component"
ENTRY_TYPES = {
  ENTITY_TYPE,
  COMPONENT_TYPE,
}

ENTITY_REQUIRED_KEYS = {
  "id",
  "type",
  "children",
}

ENTITY_OPTIONAL_KEYS = {
  "name",
}

COMPONENT_REQUIRED_KEYS = {
  "type",
  "name",
}

COMPONENT_SOURCE_KEYS = {
  "iotDeviceId",
  "componentTypeId",
}

COMPONENT_OPTIONAL_KEYS = COMPONENT_SOURCE_KEYS | {"componentTypeName"}

ENTITY_ID_PATTERN = r"[A-Za-z0-9_-]+"
IOT_DEVICE_ID_PATTERN = r"[A-Za-z0-9_-]+"
COMPONENT_NAME_PATTERN = r"[A-Za-z0-9_-]+"
COMPONENT_TYPE_ID_PATTERN = r"[A-Za-z0-9_.:-]+"


def validate(config):
  require_list(config, CONFIG_NAME)

  seen_entity_ids = set()

  for index, entry in enumerate(config):
    _validate_root_entity(entry, f"{CONFIG_NAME}[{index}]", seen_entity_ids)


def _validate_root_entity(entry, field, seen_entity_ids):
  require_dict(entry, field)
  require_keys(entry, {"type"}, field)
  _validate_entry_type(entry["type"], f"{field}.type", {ENTITY_TYPE})
  _validate_entity(entry, field, seen_entity_ids)


def _validate_entity(entity, field, seen_entity_ids):
  require_dict(entity, field)
  require_keys(entity, ENTITY_REQUIRED_KEYS, field)
  require_no_unknown_keys(
    entity,
    ENTITY_REQUIRED_KEYS | ENTITY_OPTIONAL_KEYS,
    field,
  )

  _validate_entry_type(entity["type"], f"{field}.type", {ENTITY_TYPE})
  _validate_entity_id(entity["id"], f"{field}.id", seen_entity_ids)

  if "name" in entity:
    require_string(entity["name"], f"{field}.name")

  _validate_children(entity["children"], f"{field}.children", seen_entity_ids)


def _validate_children(children, field, seen_entity_ids):
  require_list(children, field)

  seen_component_names = set()

  for index, entry in enumerate(children):
    child_field = f"{field}[{index}]"

    require_dict(entry, child_field)
    require_keys(entry, {"type"}, child_field)

    if entry["type"] == ENTITY_TYPE:
      _validate_entity(entry, child_field, seen_entity_ids)
    elif entry["type"] == COMPONENT_TYPE:
      _validate_component(entry, child_field, seen_component_names)
    else:
      _validate_entry_type(entry["type"], f"{child_field}.type", ENTRY_TYPES)


def _validate_component(component, field, seen_component_names):
  require_dict(component, field)
  require_keys(component, COMPONENT_REQUIRED_KEYS, field)
  require_no_unknown_keys(
    component,
    COMPONENT_REQUIRED_KEYS | COMPONENT_OPTIONAL_KEYS,
    field,
  )

  _validate_entry_type(component["type"], f"{field}.type", {COMPONENT_TYPE})
  _validate_component_name(
    component["name"],
    f"{field}.name",
    seen_component_names,
  )
  if "componentTypeName" in component:
    require_string(component["componentTypeName"], f"{field}.componentTypeName")

  _validate_component_type_source(component, field)


def _validate_entry_type(value, field, allowed_types):
  require_string(value, field)

  if value not in allowed_types:
    raise ValueError(f"{field} must be one of: {keys_text(allowed_types)}")


def _validate_entity_id(value, field, seen_entity_ids):
  require_string(value, field)

  if not re.fullmatch(ENTITY_ID_PATTERN, value):
    raise ValueError(f"{field} must match regex: {ENTITY_ID_PATTERN}")

  if value in seen_entity_ids:
    raise ValueError(f"{field} is duplicated: {value}")

  seen_entity_ids.add(value)


def _validate_component_name(value, field, seen_component_names):
  require_string(value, field)

  if not re.fullmatch(COMPONENT_NAME_PATTERN, value):
    raise ValueError(f"{field} must match regex: {COMPONENT_NAME_PATTERN}")

  if value in seen_component_names:
    raise ValueError(f"{field} is duplicated in the same entity: {value}")

  seen_component_names.add(value)


def _validate_component_type_source(component, field):
  source_keys = COMPONENT_SOURCE_KEYS & component.keys()

  if not source_keys:
    raise ValueError(
      f"{field} must contain at least one of: {keys_text(COMPONENT_SOURCE_KEYS)}"
    )

  if "iotDeviceId" in component:
    _validate_iot_device_id(component["iotDeviceId"], f"{field}.iotDeviceId")

  if "componentTypeId" in component:
    _validate_component_type_id(
      component["componentTypeId"],
      f"{field}.componentTypeId",
    )


def _validate_iot_device_id(value, field):
  require_string(value, field)

  if not re.fullmatch(IOT_DEVICE_ID_PATTERN, value):
    raise ValueError(f"{field} must match regex: {IOT_DEVICE_ID_PATTERN}")


def _validate_component_type_id(value, field):
  require_string(value, field)

  if not re.fullmatch(COMPONENT_TYPE_ID_PATTERN, value):
    raise ValueError(
      f"{field} must match regex: {COMPONENT_TYPE_ID_PATTERN}"
    )
