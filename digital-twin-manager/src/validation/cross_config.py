from deployers.aws.iot.device_config import infer_iot_device_id, iot_device_ids_by_component_type


CONFIG_NAME = "cross-config"

AWS_PROVIDER = "aws"


def validate(
  config_providers,
  config_iot_devices,
  config_hierarchy,
  config_events,
  config=None,
):
  _validate_provider_compatibility(
    config_providers,
    config_iot_devices,
    config_hierarchy,
    config_events,
  )

  iot_devices_by_id = _iot_devices_by_id(config_iot_devices)
  hierarchy_entities = _hierarchy_entities(config_hierarchy)

  _validate_hierarchy_iot_device_references(
    config_hierarchy,
    iot_devices_by_id,
    iot_device_ids_by_component_type(config, config_iot_devices, config_hierarchy) if config is not None else {},
  )
  _validate_event_condition_references(
    config_events,
    hierarchy_entities,
    iot_devices_by_id,
  )
  _validate_event_input_parameter_references(
    config_events,
    hierarchy_entities,
    iot_devices_by_id,
  )
  _validate_event_feedback_iot_device_references(
    config_events,
    iot_devices_by_id,
  )


def _validate_provider_compatibility(
  config_providers,
  config_iot_devices,
  config_hierarchy,
  config_events,
):
  if config_iot_devices:
    _require_provider(
      config_providers,
      "layer_1_provider",
      "config_iot_devices.json IoT Things and MQTT ingestion",
    )
    _require_provider(
      config_providers,
      "layer_2_provider",
      "config_iot_devices.json processor Lambdas",
    )
    _require_provider(
      config_providers,
      "layer_4_provider",
      "config_iot_devices.json TwinMaker Component Types",
    )

  if config_hierarchy:
    _require_provider(
      config_providers,
      "layer_4_provider",
      "config_hierarchy.json TwinMaker hierarchy",
    )

  if config_events:
    _require_provider(
      config_providers,
      "layer_2_provider",
      "config_events.json Event-Checker and action Lambdas",
    )
    _require_provider(
      config_providers,
      "layer_4_provider",
      "config_events.json condition value lookup through TwinMaker",
    )

  if _has_mqtt_feedback(config_events):
    _require_provider(
      config_providers,
      "layer_1_provider",
      "config_events.json MQTT feedback",
    )


def _validate_hierarchy_iot_device_references(
  config_hierarchy,
  iot_devices_by_id,
  device_ids_by_type,
):
  for index, entity in enumerate(config_hierarchy):
    _validate_entity_iot_device_references(
      entity,
      f"config_hierarchy.json[{index}]",
      iot_devices_by_id,
      device_ids_by_type,
    )


def _validate_entity_iot_device_references(
  entity,
  field,
  iot_devices_by_id,
  device_ids_by_type,
):
  for index, child in enumerate(entity["children"]):
    child_field = f"{field}.children[{index}]"

    if child["type"] == "entity":
      _validate_entity_iot_device_references(
        child,
        child_field,
        iot_devices_by_id,
        device_ids_by_type,
      )
    elif child["type"] == "component" and "iotDeviceId" in child:
      iot_device_id = child["iotDeviceId"]

      if iot_device_id not in iot_devices_by_id:
        raise ValueError(
          f"{child_field}.iotDeviceId references unknown "
          f"config_iot_devices.json id: {iot_device_id}"
        )
    elif child["type"] == "component":
      infer_iot_device_id(child["componentTypeId"], device_ids_by_type)


def _validate_event_condition_references(
  config_events,
  hierarchy_entities,
  iot_devices_by_id,
):
  for index, event in enumerate(config_events):
    condition = event["condition"]
    left_operand, _, right_operand = condition.split()

    _validate_event_condition_operand_reference(
      left_operand,
      f"config_events.json[{index}].condition.left",
      hierarchy_entities,
      iot_devices_by_id,
    )
    _validate_event_condition_operand_reference(
      right_operand,
      f"config_events.json[{index}].condition.right",
      hierarchy_entities,
      iot_devices_by_id,
    )


def _validate_event_condition_operand_reference(
  operand,
  field,
  hierarchy_entities,
  iot_devices_by_id,
):
  _referenced_iot_property(
    operand,
    field,
    hierarchy_entities,
    iot_devices_by_id,
  )


def _validate_event_input_parameter_references(
  config_events,
  hierarchy_entities,
  iot_devices_by_id,
):
  for event_index, event in enumerate(config_events):
    input_parameters = event["action"].get("inputParameters", [])

    for parameter_index, parameter in enumerate(input_parameters):
      reference = parameter.get("id")

      if reference is None:
        continue

      parameter_field = (
        f"config_events.json[{event_index}].action."
        f"inputParameters[{parameter_index}]"
      )
      iot_property = _referenced_iot_property(
        reference,
        f"{parameter_field}.id",
        hierarchy_entities,
        iot_devices_by_id,
      )

      if iot_property is None:
        continue

      parameter_data_type = parameter["dataType"]
      property_data_type = iot_property["dataType"]

      if parameter_data_type != property_data_type:
        raise ValueError(
          f"{parameter_field}.dataType is '{parameter_data_type}', but "
          f"the referenced property dataType is '{property_data_type}'."
        )


def _referenced_iot_property(
  reference,
  field,
  hierarchy_entities,
  iot_devices_by_id,
):
  parts = reference.split(".")

  if len(parts) != 3:
    return

  entity_id, component_name, property_name = parts
  entity = hierarchy_entities.get(entity_id)

  if entity is None:
    raise ValueError(
      f"{field} references unknown config_hierarchy.json entity: {entity_id}"
    )

  component = entity["components"].get(component_name)

  if component is None:
    raise ValueError(
      f"{field} references unknown component '{component_name}' "
      f"on config_hierarchy.json entity: {entity_id}"
    )

  iot_device_id = component.get("iotDeviceId")

  if iot_device_id is None:
    return

  iot_device = iot_devices_by_id.get(iot_device_id)

  if iot_device is None:
    raise ValueError(
      f"{field} references component '{component_name}' backed by unknown "
      f"config_iot_devices.json id: {iot_device_id}"
    )

  properties_by_name = _iot_device_properties_by_name(iot_device)
  iot_property = properties_by_name.get(property_name)

  if iot_property is None:
    raise ValueError(
      f"{field} references unknown property '{property_name}' on "
      f"config_iot_devices.json device: {iot_device_id}"
    )

  return iot_property


def _validate_event_feedback_iot_device_references(
  config_events,
  iot_devices_by_id,
):
  for index, event in enumerate(config_events):
    feedback = event["action"].get("feedback")

    if feedback is None or "iotDeviceId" not in feedback:
      continue

    iot_device_id = feedback["iotDeviceId"]

    if iot_device_id not in iot_devices_by_id:
      raise ValueError(
        f"config_events.json[{index}].action.feedback.iotDeviceId "
        "references unknown config_iot_devices.json id: "
        f"{iot_device_id}"
      )


def _iot_devices_by_id(config_iot_devices):
  return {
    iot_device["id"]: iot_device
    for iot_device in config_iot_devices
  }


def _iot_device_properties_by_name(iot_device):
  return {
    iot_property["name"]: iot_property
    for iot_property in iot_device["properties"]
  }


def _hierarchy_entities(config_hierarchy):
  entities = {}

  for entity in config_hierarchy:
    _collect_hierarchy_entity(entity, entities)

  return entities


def _collect_hierarchy_entity(entity, entities):
  entity_info = {
    "components": {},
  }
  entities[entity["id"]] = entity_info

  for child in entity["children"]:
    if child["type"] == "entity":
      _collect_hierarchy_entity(child, entities)
    elif child["type"] == "component":
      entity_info["components"][child["name"]] = child


def _has_mqtt_feedback(config_events):
  for event in config_events:
    feedback = event["action"].get("feedback")

    if feedback is not None and feedback["type"] == "mqtt":
      return True

  return False


def _require_provider(config_providers, provider_key, feature):
  provider = config_providers.get(provider_key)

  if provider != AWS_PROVIDER:
    raise ValueError(
      f"{CONFIG_NAME}: {feature} requires "
      f"config_providers.json.{provider_key} to be '{AWS_PROVIDER}'."
    )
