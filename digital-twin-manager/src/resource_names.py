from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


IOT_AUTH_FILES_DIR = "iot_devices_auth"


def digital_twin_name(config: Mapping[str, Any]) -> str:
  value = config["digital_twin_name"]

  if not isinstance(value, str):
    raise ValueError("Config field 'digital_twin_name' must be a string.")

  return value


def resource_name_from_digital_twin_name(
  digital_twin_name: str,
  logical_name: str,
) -> str:
  return f"{digital_twin_name}-{logical_name}"


def resource_name(config: Mapping[str, Any], logical_name: str) -> str:
  return resource_name_from_digital_twin_name(digital_twin_name(config), logical_name)


def iot_rule_name(config: Mapping[str, Any], logical_name: str) -> str:
  return resource_name(config, logical_name).replace("-", "_")


def s3_bucket_name(config: Mapping[str, Any], logical_name: str) -> str:
  return resource_name(config, logical_name).lower()


def dispatcher_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "dispatcher")


def dispatcher_lambda_function_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "dispatcher")


def dispatcher_iot_rule_name(config: Mapping[str, Any]) -> str:
  return iot_rule_name(config, "trigger-dispatcher")


def dispatcher_iot_rule_topic(config: Mapping[str, Any]) -> str:
  return f"{digital_twin_name(config)}/iot-data"


def persister_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "persister")


def persister_lambda_function_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "persister")


def event_feedback_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "event-feedback")


def event_feedback_lambda_function_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "event-feedback")


def event_checker_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "event-checker")


def event_checker_lambda_function_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "event-checker")


def lambda_chain_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "lambda-chain")


def lambda_chain_step_function_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "lambda-chain")


def hot_dynamodb_table_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "hot-iot-data")


def hot_cold_mover_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "hot-to-cold-mover")


def hot_cold_mover_lambda_function_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "hot-to-cold-mover")


def hot_cold_mover_event_rule_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "hot-to-cold-mover")


def hot_reader_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "hot-reader")


def hot_reader_lambda_function_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "hot-reader")


def cold_s3_bucket_name(config: Mapping[str, Any]) -> str:
  return s3_bucket_name(config, "cold-iot-data")


def cold_archive_mover_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "cold-to-archive-mover")


def cold_archive_mover_lambda_function_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "cold-to-archive-mover")


def cold_archive_mover_event_rule_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "cold-to-archive-mover")


def archive_s3_bucket_name(config: Mapping[str, Any]) -> str:
  return s3_bucket_name(config, "archive-iot-data")


def twinmaker_s3_bucket_name(config: Mapping[str, Any]) -> str:
  return s3_bucket_name(config, "twinmaker")


def twinmaker_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "twinmaker")


def twinmaker_workspace_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "twinmaker")


def grafana_workspace_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "grafana")


def grafana_iam_role_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "grafana")


def iot_thing_name(config: Mapping[str, Any], iot_device: Mapping[str, Any]) -> str:
  return resource_name(config, str(iot_device["id"]))


def iot_policy_name(config: Mapping[str, Any]) -> str:
  return resource_name(config, "iot-policy")


def iot_thing_policy_name(
  config: Mapping[str, Any],
  iot_device: Mapping[str, Any],
) -> str:
  """Name of a legacy per-device policy, retained for migration and cleanup."""
  return resource_name(config, str(iot_device["id"]))


def iot_auth_files_path(device_id: str) -> str:
  return f"{IOT_AUTH_FILES_DIR}/{device_id}"


def processor_lambda_function_name_local(iot_device: Mapping[str, Any]) -> str:
  return str(iot_device["id"])


def processor_logical_name(iot_device: Mapping[str, Any]) -> str:
  return processor_logical_name_from_device_id(
    processor_lambda_function_name_local(iot_device)
  )


def processor_logical_name_from_device_id(device_id: str) -> str:
  return f"{device_id}-processor"


def processor_iam_role_name(
  config: Mapping[str, Any],
  iot_device: Mapping[str, Any],
) -> str:
  return resource_name(config, processor_logical_name(iot_device))


def processor_lambda_function_name(
  config: Mapping[str, Any],
  iot_device: Mapping[str, Any],
) -> str:
  return resource_name(config, processor_logical_name(iot_device))


def component_type_logical_id(iot_device: Mapping[str, Any]) -> str:
  return str(iot_device.get("componentTypeId") or iot_device["id"])


def twinmaker_component_type_id(
  config: Mapping[str, Any],
  iot_device: Mapping[str, Any],
) -> str:
  return twinmaker_component_type_id_from_device_id(
    config, component_type_logical_id(iot_device)
  )


def twinmaker_component_type_id_from_device_id(
  config: Mapping[str, Any],
  device_id: str,
) -> str:
  return resource_name(config, device_id)


def hierarchy_component_type_id(
  config: Mapping[str, Any],
  component: Mapping[str, Any],
) -> str:
  if "componentTypeId" in component:
    if "iotDeviceId" in component:
      return twinmaker_component_type_id_from_device_id(
        config, str(component["componentTypeId"])
      )
    return component["componentTypeId"]
  return twinmaker_component_type_id_from_device_id(
    config, str(component["iotDeviceId"])
  )


def event_action_iam_role_name(
  config: Mapping[str, Any],
  event_action: Mapping[str, Any],
) -> str:
  return resource_name(config, str(event_action["functionName"]))


def event_action_lambda_function_name(
  config: Mapping[str, Any],
  event_action: Mapping[str, Any],
) -> str:
  return resource_name(config, str(event_action["functionName"]))


def event_action_id(event: Mapping[str, Any]) -> str:
  payload = json.dumps(
    event,
    sort_keys=True,
    separators=(",", ":"),
  )
  digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
  action = event.get("action", {})
  action_type = action.get("type", "unknown")
  function_name = action.get("functionName", "unknown")
  return f"{action_type}:{function_name}:{digest}"


def ssm_registry_prefix(config: Mapping[str, Any]) -> str:
  return f"/{digital_twin_name(config)}/event-registry"
