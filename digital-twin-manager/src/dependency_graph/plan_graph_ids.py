from __future__ import annotations

from typing import Any, Mapping

import resource_names

from .graph_ids import runtime_node_id


DISPATCHER_IAM = runtime_node_id("core:l1:dispatcher_iam:iam", "dispatcher")
DISPATCHER_LAMBDA = runtime_node_id(
  "core:l1:dispatcher_lambda:lambda_function",
  "dispatcher",
)
DISPATCHER_IOT_RULE = runtime_node_id(
  "core:l1:dispatcher_iot_rule:iot_rule",
  "trigger-dispatcher",
)
DISPATCHER_IOT_RULE_LAMBDA_PERMISSION = runtime_node_id(
  "core:l1:dispatcher_iot_rule_lambda_permission:lambda_permission",
  "trigger-dispatcher",
)

PERSISTER_IAM = runtime_node_id("core:l2:persister_iam:iam", "persister")
PERSISTER_LAMBDA = runtime_node_id(
  "core:l2:persister_lambda:lambda_function",
  "persister",
)
EVENT_FEEDBACK_IAM = runtime_node_id(
  "core:l2:event_feedback_iam:iam",
  "event-feedback",
)
EVENT_FEEDBACK_LAMBDA = runtime_node_id(
  "core:l2:event_feedback_lambda:lambda_function",
  "event-feedback",
)
EVENT_CHECKER_IAM = runtime_node_id(
  "core:l2:event_checker_iam:iam",
  "event-checker",
)
EVENT_CHECKER_LAMBDA = runtime_node_id(
  "core:l2:event_checker_lambda:lambda_function",
  "event-checker",
)
LAMBDA_CHAIN_IAM = runtime_node_id(
  "core:l2:lambda_chain_iam:iam",
  "lambda-chain",
)
LAMBDA_CHAIN_STEP_FUNCTION = runtime_node_id(
  "core:l2:lambda_chain_step_function:step_function",
  "lambda-chain",
)

HOT_DYNAMODB_TABLE = runtime_node_id(
  "core:l3_hot:hot_dynamodb_table:dynamodb_table",
  "hot-iot-data",
)
HOT_COLD_MOVER_IAM = runtime_node_id(
  "core:l3_hot:hot_cold_mover_iam:iam",
  "hot-to-cold-mover",
)
HOT_COLD_MOVER_LAMBDA = runtime_node_id(
  "core:l3_hot:hot_cold_mover_lambda:lambda_function",
  "hot-to-cold-mover",
)
HOT_COLD_MOVER_EVENT_RULE = runtime_node_id(
  "core:l3_hot:hot_cold_mover_event_rule:eventbridge_rule",
  "hot-to-cold-mover",
)
HOT_READER_IAM = runtime_node_id(
  "core:l3_hot:hot_reader_iam:iam",
  "hot-reader",
)
HOT_READER_LAMBDA = runtime_node_id(
  "core:l3_hot:hot_reader_lambda:lambda_function",
  "hot-reader",
)

COLD_S3_BUCKET = runtime_node_id(
  "core:l3_cold:cold_s3_bucket:s3_bucket",
  "cold-iot-data",
)
COLD_ARCHIVE_MOVER_IAM = runtime_node_id(
  "core:l3_cold:cold_archive_mover_iam:iam",
  "cold-to-archive-mover",
)
COLD_ARCHIVE_MOVER_LAMBDA = runtime_node_id(
  "core:l3_cold:cold_archive_mover_lambda:lambda_function",
  "cold-to-archive-mover",
)
COLD_ARCHIVE_MOVER_EVENT_RULE = runtime_node_id(
  "core:l3_cold:cold_archive_mover_event_rule:eventbridge_rule",
  "cold-to-archive-mover",
)

ARCHIVE_S3_BUCKET = runtime_node_id(
  "core:l3_archive:archive_s3_bucket:s3_bucket",
  "archive-iot-data",
)

TWINMAKER_S3_BUCKET = runtime_node_id(
  "core:l4:twinmaker_s3_bucket:s3_bucket",
  "twinmaker",
)
TWINMAKER_IAM = runtime_node_id("core:l4:twinmaker_iam:iam", "twinmaker")
TWINMAKER_WORKSPACE = runtime_node_id(
  "core:l4:twinmaker_workspace:twinmaker_workspace",
  "twinmaker",
)

GRAFANA_IAM = runtime_node_id("core:l5:grafana_iam:iam", "grafana")
GRAFANA_WORKSPACE = runtime_node_id(
  "core:l5:grafana_workspace:grafana_workspace",
  "grafana",
)

IOT_POLICY = runtime_node_id("iot:l1:iot_policy:iot_policy", "iot-policy")


def iot_thing(iot_device: Mapping[str, Any]) -> str:
  return runtime_node_id("iot:l1:iot_thing:iot_thing", str(iot_device["id"]))


def processor_iam(iot_device: Mapping[str, Any]) -> str:
  return runtime_node_id(
    "iot:l2:processor_iam:iam",
    resource_names.processor_logical_name(iot_device),
  )


def processor_lambda(iot_device: Mapping[str, Any]) -> str:
  return runtime_node_id(
    "iot:l2:processor_lambda:lambda_function",
    resource_names.processor_logical_name(iot_device),
  )


def device_component_type(component_type_logical_id: str) -> str:
  return runtime_node_id(
    "iot:l4:device_component_type:twinmaker_component_type",
    component_type_logical_id,
  )


def twinmaker_hierarchy(entity_id: str) -> str:
  return runtime_node_id(
    "hierarchy:hierarchy:twinmaker_hierarchy:twinmaker_hierarchy",
    entity_id,
  )


def event_action(action_id: str) -> str:
  return runtime_node_id(
    "event_actions:event_actions:event_action:event_action",
    action_id,
  )


def init_value(iot_device_id: str) -> str:
  return runtime_node_id(
    "init_values:init_values:init_value:init_value",
    iot_device_id,
  )
