from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import resource_names
from deployers.aws.iot.device_config import effective_iot_devices

from .graph_ids import runtime_node_id
from .models import RuntimeDependency, RuntimeGraph, RuntimeNode, TemplateGraph, TemplateNode


IOT_L4_COMPONENT_TYPE_TEMPLATE_ID = "iot:l4:device_component_type:twinmaker_component_type"
HIERARCHY_TEMPLATE_ID = "hierarchy:hierarchy:twinmaker_hierarchy:twinmaker_hierarchy"
HIERARCHY_ENTITY_TEMPLATE_ID = "hierarchy:hierarchy:twinmaker_entity:twinmaker_entity"
EVENT_ACTION_TEMPLATE_ID = "event_actions:event_actions:event_action:event_action"
EVENT_ACTION_IAM_TEMPLATE_ID = "event_actions:event_actions:event_action_iam:iam"
INIT_VALUE_TEMPLATE_ID = "init_values:init_values:init_value:init_value"


SHARED_LOGICAL_NAMES = {
  "iot:l1:iot_policy:iot_policy": "iot-policy",
  "iot:l1:iot_policy_version:iot_policy_version": "iot-policy",
  "core:l1:dispatcher_iam:iam": "dispatcher",
  "core:l1:dispatcher_iam_managed_policy_attachment:iam_managed_policy_attachment": "dispatcher",
  "core:l1:dispatcher_lambda:lambda_function": "dispatcher",
  "core:l1:dispatcher_iot_rule:iot_rule": "trigger-dispatcher",
  "core:l1:dispatcher_iot_rule_lambda_permission:lambda_permission": "trigger-dispatcher",
  "core:l2:persister_iam:iam": "persister",
  "core:l2:persister_iam_managed_policy_attachment:iam_managed_policy_attachment": "persister",
  "core:l2:persister_lambda:lambda_function": "persister",
  "core:l2:event_feedback_iam:iam": "event-feedback",
  "core:l2:event_feedback_iam_managed_policy_attachment:iam_managed_policy_attachment": "event-feedback",
  "core:l2:event_feedback_lambda:lambda_function": "event-feedback",
  "core:l2:event_checker_iam:iam": "event-checker",
  "core:l2:event_checker_iam_managed_policy_attachment:iam_managed_policy_attachment": "event-checker",
  "core:l2:event_checker_iam_inline_policy:iam_inline_policy": "event-checker",
  "core:l2:event_checker_lambda:lambda_function": "event-checker",
  "core:l2:lambda_chain_iam:iam": "lambda-chain",
  "core:l2:lambda_chain_iam_managed_policy_attachment:iam_managed_policy_attachment": "lambda-chain",
  "core:l2:lambda_chain_step_function:step_function": "lambda-chain",
  "core:l3_hot:hot_dynamodb_table:dynamodb_table": "hot-iot-data",
  "core:l3_hot:hot_dynamodb_backup:dynamodb_backup": "hot-iot-data-backup",
  "core:l3_hot:hot_cold_mover_iam:iam": "hot-to-cold-mover",
  "core:l3_hot:hot_cold_mover_iam_managed_policy_attachment:iam_managed_policy_attachment": "hot-to-cold-mover",
  "core:l3_hot:hot_cold_mover_lambda:lambda_function": "hot-to-cold-mover",
  "core:l3_hot:hot_cold_mover_event_rule:eventbridge_rule": "hot-to-cold-mover",
  "core:l3_hot:hot_cold_mover_event_target:eventbridge_target": "hot-to-cold-mover",
  "core:l3_hot:hot_cold_mover_lambda_permission:lambda_permission": "hot-to-cold-mover",
  "core:l3_hot:hot_reader_iam:iam": "hot-reader",
  "core:l3_hot:hot_reader_iam_managed_policy_attachment:iam_managed_policy_attachment": "hot-reader",
  "core:l3_hot:hot_reader_iam_inline_policy:iam_inline_policy": "hot-reader",
  "core:l3_hot:hot_reader_lambda:lambda_function": "hot-reader",
  "core:l3_hot:hot_reader_twinmaker_lambda_permission:lambda_permission": "hot-reader",
  "core:l3_cold:cold_s3_bucket:s3_bucket": "cold-iot-data",
  "core:l3_cold:cold_archive_mover_iam:iam": "cold-to-archive-mover",
  "core:l3_cold:cold_archive_mover_iam_managed_policy_attachment:iam_managed_policy_attachment": "cold-to-archive-mover",
  "core:l3_cold:cold_archive_mover_lambda:lambda_function": "cold-to-archive-mover",
  "core:l3_cold:cold_archive_mover_event_rule:eventbridge_rule": "cold-to-archive-mover",
  "core:l3_cold:cold_archive_mover_event_target:eventbridge_target": "cold-to-archive-mover",
  "core:l3_cold:cold_archive_mover_lambda_permission:lambda_permission": "cold-to-archive-mover",
  "core:l3_archive:archive_s3_bucket:s3_bucket": "archive-iot-data",
  "core:l4:twinmaker_s3_bucket:s3_bucket": "twinmaker",
  "core:l4:twinmaker_s3_bucket_cors:s3_bucket_cors": "twinmaker",
  "core:l4:twinmaker_iam:iam": "twinmaker",
  "core:l4:twinmaker_iam_inline_policy:iam_inline_policy": "twinmaker",
  "core:l4:twinmaker_workspace:twinmaker_workspace": "twinmaker",
  "core:l4:twinmaker_workspace_scene_cleanup:twinmaker_scene": "twinmaker",
  "core:l4:twinmaker_workspace_entity_cleanup:twinmaker_entity": "twinmaker",
  "core:l4:twinmaker_workspace_component_type_cleanup:twinmaker_component_type": "twinmaker",
  "core:l5:grafana_iam:iam": "grafana",
  "core:l5:grafana_iam_trust_policy:iam_trust_policy": "grafana",
  "core:l5:grafana_iam_inline_policy:iam_inline_policy": "grafana",
  "core:l5:grafana_workspace:grafana_workspace": "grafana",
}


@dataclass(frozen=True)
class _RuntimeNodeDraft:
  template: TemplateNode
  logical_name: str
  physical_name: str | None
  metadata: dict[str, Any]

  @property
  def id(self) -> str:
    return _runtime_id(self.template.id, self.logical_name)


@dataclass(frozen=True)
class _HierarchyEntity:
  entity: Mapping[str, Any]
  root_entity_id: str
  parent_entity_id: str | None


@dataclass(frozen=True)
class _HierarchyComponent:
  component: Mapping[str, Any]
  root_entity_id: str
  parent_entity_id: str


def build_runtime_graph(
  template_graph: TemplateGraph,
  config: Mapping[str, Any],
  config_iot_devices: Sequence[Mapping[str, Any]],
  config_events: Sequence[Mapping[str, Any]],
  config_hierarchy: Sequence[Mapping[str, Any]],
) -> RuntimeGraph:
  drafts: list[_RuntimeNodeDraft] = []

  for template in template_graph.templates:
    drafts.extend(
      _template_drafts(
        template,
        config,
        config_iot_devices,
        config_events,
        config_hierarchy,
      )
    )

  _validate_unique_runtime_ids(drafts)
  drafts_by_template = _drafts_by_template_id(drafts)

  nodes = [
    RuntimeNode(
      id=draft.id,
      template_id=draft.template.id,
      owner_deployer=draft.template.owner_deployer,
      logical_name=draft.logical_name,
      physical_name=draft.physical_name,
      depends_on=_runtime_dependencies(draft, drafts_by_template),
      lifecycle_artifact=draft.template.lifecycle_artifact,
    )
    for draft in drafts
  ]

  return RuntimeGraph(version=template_graph.version, nodes=tuple(nodes))


def _template_drafts(
  template: TemplateNode,
  config: Mapping[str, Any],
  config_iot_devices: Sequence[Mapping[str, Any]],
  config_events: Sequence[Mapping[str, Any]],
  config_hierarchy: Sequence[Mapping[str, Any]],
) -> list[_RuntimeNodeDraft]:
  template_id = template.id

  if template_id in SHARED_LOGICAL_NAMES:
    return [_shared_draft(template, config)]

  if template_id.startswith("iot:l1:"):
    return [
      _iot_l1_draft(template, config, iot_device)
      for iot_device in effective_iot_devices(config_iot_devices)
    ]

  if template_id.startswith("iot:l2:"):
    return [
      _iot_l2_draft(template, config, iot_device)
      for iot_device in effective_iot_devices(config_iot_devices)
    ]

  if template_id.startswith("iot:l4:"):
    representative_devices: dict[str, Mapping[str, Any]] = {}

    for iot_device in effective_iot_devices(config_iot_devices, config_hierarchy):
      component_type_logical_name = resource_names.component_type_logical_id(iot_device)
      representative_devices.setdefault(component_type_logical_name, iot_device)

    return [
      _iot_l4_draft(template, config, iot_device)
      for iot_device in representative_devices.values()
    ]

  if template_id == HIERARCHY_TEMPLATE_ID:
    return _hierarchy_root_drafts(template, config, config_hierarchy)

  if template_id == HIERARCHY_ENTITY_TEMPLATE_ID:
    return _hierarchy_entity_drafts(template, config_hierarchy)

  if template_id == "hierarchy:hierarchy:twinmaker_component:twinmaker_component":
    return _hierarchy_component_drafts(template, config, config_hierarchy)

  if template_id.startswith("event_actions:event_actions:"):
    return _event_action_drafts(template, config, config_events)

  if template_id.startswith("init_values:init_values:"):
    return _init_value_drafts(template, config_iot_devices)

  return [_shared_draft(template, config)]


def _shared_draft(
  template: TemplateNode,
  config: Mapping[str, Any],
) -> _RuntimeNodeDraft:
  logical_name = _shared_logical_name(template.id)

  return _RuntimeNodeDraft(
    template=template,
    logical_name=logical_name,
    physical_name=_shared_physical_name(template.id, logical_name, config),
    metadata={"scope": "shared"},
  )


def _iot_l1_draft(
  template: TemplateNode,
  config: Mapping[str, Any],
  iot_device: Mapping[str, Any],
) -> _RuntimeNodeDraft:
  device_id = str(iot_device["id"])

  return _RuntimeNodeDraft(
    template=template,
    logical_name=device_id,
    physical_name=_iot_l1_physical_name(template.id, config, device_id),
    metadata={"scope": "iot_device", "device_id": device_id},
  )


def _iot_l2_draft(
  template: TemplateNode,
  config: Mapping[str, Any],
  iot_device: Mapping[str, Any],
) -> _RuntimeNodeDraft:
  device_id = str(iot_device["id"])
  logical_name = resource_names.processor_logical_name_from_device_id(device_id)

  return _RuntimeNodeDraft(
    template=template,
    logical_name=logical_name,
    physical_name=resource_names.resource_name(config, logical_name),
    metadata={
      "scope": "iot_processor",
      "device_id": device_id,
    },
  )


def _iot_l4_draft(
  template: TemplateNode,
  config: Mapping[str, Any],
  iot_device: Mapping[str, Any],
) -> _RuntimeNodeDraft:
  component_type_logical_name = resource_names.component_type_logical_id(iot_device)

  return _RuntimeNodeDraft(
    template=template,
    logical_name=component_type_logical_name,
    physical_name=resource_names.resource_name(config, component_type_logical_name),
    metadata={
      "scope": "iot_device_component_type",
      "component_type_logical_name": component_type_logical_name,
    },
  )


def _hierarchy_root_drafts(
  template: TemplateNode,
  config: Mapping[str, Any],
  config_hierarchy: Sequence[Mapping[str, Any]],
) -> list[_RuntimeNodeDraft]:
  drafts = []

  for root in config_hierarchy:
    root_entity_id = str(root["id"])
    drafts.append(
      _RuntimeNodeDraft(
        template=template,
        logical_name=root_entity_id,
        physical_name=root_entity_id,
        metadata={
          "scope": "hierarchy_root",
          "root_entity_id": root_entity_id,
          "component_type_logical_names": _component_type_logical_names(root, config),
        },
      )
    )

  return drafts


def _hierarchy_entity_drafts(
  template: TemplateNode,
  config_hierarchy: Sequence[Mapping[str, Any]],
) -> list[_RuntimeNodeDraft]:
  drafts = []

  for hierarchy_entity in _hierarchy_entities(config_hierarchy):
    entity_id = str(hierarchy_entity.entity["id"])
    metadata: dict[str, Any] = {
      "scope": "hierarchy_entity",
      "root_entity_id": hierarchy_entity.root_entity_id,
      "entity_id": entity_id,
    }

    if hierarchy_entity.parent_entity_id is not None:
      metadata["parent_entity_id"] = hierarchy_entity.parent_entity_id

    drafts.append(
      _RuntimeNodeDraft(
        template=template,
        logical_name=entity_id,
        physical_name=entity_id,
        metadata=metadata,
      )
    )

  return drafts


def _hierarchy_component_drafts(
  template: TemplateNode,
  config: Mapping[str, Any],
  config_hierarchy: Sequence[Mapping[str, Any]],
) -> list[_RuntimeNodeDraft]:
  drafts = []

  for hierarchy_component in _hierarchy_components(config_hierarchy):
    component = hierarchy_component.component
    component_name = str(component["name"])
    parent_entity_id = hierarchy_component.parent_entity_id
    component_type_logical_name = _component_type_logical_name(component, config)

    drafts.append(
      _RuntimeNodeDraft(
        template=template,
        logical_name=f"{parent_entity_id}.{component_name}",
        physical_name=f"{parent_entity_id}.{component_name}",
        metadata={
          "scope": "hierarchy_component",
          "root_entity_id": hierarchy_component.root_entity_id,
          "parent_entity_id": parent_entity_id,
          "component_name": component_name,
          "component_type_logical_name": component_type_logical_name,
        },
      )
    )

  return drafts


def _event_action_drafts(
  template: TemplateNode,
  config: Mapping[str, Any],
  config_events: Sequence[Mapping[str, Any]],
) -> list[_RuntimeNodeDraft]:
  drafts = []

  for event in config_events:
    if template.id != EVENT_ACTION_TEMPLATE_ID and not _event_creates_lambda(event):
      continue

    event_id = resource_names.event_action_id(event)
    action = event["action"]
    function_name = action.get("functionName")
    physical_name = event_id

    if template.id != EVENT_ACTION_TEMPLATE_ID and function_name:
      physical_name = resource_names.resource_name(config, str(function_name))

    drafts.append(
      _RuntimeNodeDraft(
        template=template,
        logical_name=event_id,
        physical_name=physical_name,
        metadata={
          "scope": "event_action",
          "event_id": event_id,
          "function_name": function_name,
        },
      )
    )

  return drafts


def _init_value_drafts(
  template: TemplateNode,
  config_iot_devices: Sequence[Mapping[str, Any]],
) -> list[_RuntimeNodeDraft]:
  drafts = []

  for iot_device in effective_iot_devices(config_iot_devices):
    if not _has_init_values(iot_device):
      continue

    device_id = str(iot_device["id"])
    drafts.append(
      _RuntimeNodeDraft(
        template=template,
        logical_name=device_id,
        physical_name=device_id,
        metadata={
          "scope": "init_value",
          "device_id": device_id,
        },
      )
    )

  return drafts


def _runtime_dependencies(
  draft: _RuntimeNodeDraft,
  drafts_by_template: Mapping[str, list[_RuntimeNodeDraft]],
) -> tuple[RuntimeDependency, ...]:
  dependencies = []

  for dependency in draft.template.depends_on:
    for dependency_id in _dependency_runtime_ids(
      draft,
      dependency.id,
      drafts_by_template,
    ):
      dependencies.append(
        RuntimeDependency(
          id=dependency_id,
          template_id=dependency.id,
          type=dependency.type,
        )
      )

  return tuple(dependencies)


def _dependency_runtime_ids(
  draft: _RuntimeNodeDraft,
  dependency_template_id: str,
  drafts_by_template: Mapping[str, list[_RuntimeNodeDraft]],
) -> list[str]:
  logical_names = _dependency_logical_names(draft, dependency_template_id)

  if logical_names is not None:
    return [_runtime_id(dependency_template_id, logical_name) for logical_name in logical_names]

  dependency_drafts = drafts_by_template.get(dependency_template_id, [])

  if len(dependency_drafts) == 1:
    return [dependency_drafts[0].id]

  return []


def _dependency_logical_names(
  draft: _RuntimeNodeDraft,
  dependency_template_id: str,
) -> list[str] | None:
  metadata = draft.metadata

  if dependency_template_id in SHARED_LOGICAL_NAMES:
    return [_shared_logical_name(dependency_template_id)]

  if dependency_template_id.startswith("iot:l1:"):
    device_id = _metadata_str(metadata, "device_id")
    return [device_id] if device_id else None

  if dependency_template_id.startswith("iot:l2:"):
    device_id = _metadata_str(metadata, "device_id")
    return (
      [resource_names.processor_logical_name_from_device_id(device_id)]
      if device_id else None
    )

  if dependency_template_id == IOT_L4_COMPONENT_TYPE_TEMPLATE_ID:
    component_type_logical_name = _metadata_str(
      metadata,
      "component_type_logical_name",
    )

    if component_type_logical_name:
      return [component_type_logical_name]

    component_type_logical_names = _metadata_strs(
      metadata,
      "component_type_logical_names",
    )
    if component_type_logical_names:
      return component_type_logical_names

    device_id = _metadata_str(metadata, "device_id")
    return [device_id] if device_id else None

  if dependency_template_id == HIERARCHY_TEMPLATE_ID:
    root_entity_id = _metadata_str(metadata, "root_entity_id")
    return [root_entity_id] if root_entity_id else None

  if dependency_template_id == HIERARCHY_ENTITY_TEMPLATE_ID:
    parent_entity_id = _metadata_str(metadata, "parent_entity_id")
    return [parent_entity_id] if parent_entity_id else None

  if dependency_template_id == EVENT_ACTION_TEMPLATE_ID:
    event_id = _metadata_str(metadata, "event_id")
    return [event_id] if event_id else None

  if dependency_template_id == EVENT_ACTION_IAM_TEMPLATE_ID:
    event_id = _metadata_str(metadata, "event_id")
    return [event_id] if event_id else None

  if dependency_template_id == INIT_VALUE_TEMPLATE_ID:
    device_id = _metadata_str(metadata, "device_id")
    return [device_id] if device_id else None

  return None


def _metadata_str(metadata: Mapping[str, Any], key: str) -> str | None:
  value = metadata.get(key)

  if value is None:
    return None

  if not isinstance(value, str):
    raise ValueError(f"Runtime metadata field '{key}' must be a string.")

  return value


def _metadata_strs(metadata: Mapping[str, Any], key: str) -> list[str]:
  value = metadata.get(key)

  if value is None:
    return []

  if not isinstance(value, (list, tuple)):
    raise ValueError(f"Runtime metadata field '{key}' must be a list of strings.")

  values: list[str] = []
  for item in value:
    if not isinstance(item, str):
      raise ValueError(f"Runtime metadata field '{key}' must be a list of strings.")

    values.append(item)

  return values


def _hierarchy_entities(
  config_hierarchy: Sequence[Mapping[str, Any]],
) -> list[_HierarchyEntity]:
  entities = []

  for root in config_hierarchy:
    root_entity_id = str(root["id"])
    _collect_hierarchy_entities(root, root_entity_id, None, entities)

  return entities


def _collect_hierarchy_entities(
  entity: Mapping[str, Any],
  root_entity_id: str,
  parent_entity_id: str | None,
  entities: list[_HierarchyEntity],
) -> None:
  entities.append(
    _HierarchyEntity(
      entity=entity,
      root_entity_id=root_entity_id,
      parent_entity_id=parent_entity_id,
    )
  )

  for child in entity.get("children", []):
    if child.get("type") == "entity":
      _collect_hierarchy_entities(
        child,
        root_entity_id,
        str(entity["id"]),
        entities,
      )


def _hierarchy_components(
  config_hierarchy: Sequence[Mapping[str, Any]],
) -> list[_HierarchyComponent]:
  components = []

  for root in config_hierarchy:
    _collect_hierarchy_components(root, str(root["id"]), components)

  return components


def _collect_hierarchy_components(
  entity: Mapping[str, Any],
  root_entity_id: str,
  components: list[_HierarchyComponent],
) -> None:
  entity_id = str(entity["id"])

  for child in entity.get("children", []):
    if child.get("type") == "entity":
      _collect_hierarchy_components(child, root_entity_id, components)
    elif child.get("type") == "component":
      components.append(
        _HierarchyComponent(
          component=child,
          root_entity_id=root_entity_id,
          parent_entity_id=entity_id,
        )
      )


def _component_type_logical_names(
  entry: Mapping[str, Any],
  config: Mapping[str, Any],
) -> tuple[str, ...]:
  logical_names: list[str] = []

  for child in entry.get("children", []):
    child_type = child.get("type")

    if child_type == "entity":
      logical_names.extend(_component_type_logical_names(child, config))
    elif child_type == "component":
      logical_names.append(_component_type_logical_name(child, config))

  return tuple(dict.fromkeys(logical_names))


def _component_type_logical_name(
  component: Mapping[str, Any],
  config: Mapping[str, Any],
) -> str:
  component_type_id = str(resource_names.hierarchy_component_type_id(config, component))
  prefix = f"{resource_names.digital_twin_name(config)}-"
  return component_type_id.removeprefix(prefix)


def _event_creates_lambda(event: Mapping[str, Any]) -> bool:
  action = event.get("action", {})
  return action.get("type") == "lambda" and not action.get("external")


def _has_init_values(iot_device: Mapping[str, Any]) -> bool:
  return any("initValue" in prop for prop in iot_device.get("properties", []))


def _iot_l1_physical_name(
  template_id: str,
  config: Mapping[str, Any],
  device_id: str,
) -> str | None:
  if template_id == "iot:l1:iot_certificate:iot_certificate":
    return None

  if template_id == "iot:l1:iot_auth_files:local_auth_files":
    return resource_names.iot_auth_files_path(device_id)

  return resource_names.resource_name(config, device_id)


def _shared_physical_name(
  template_id: str,
  logical_name: str,
  config: Mapping[str, Any],
) -> str:
  if template_id == "core:l1:dispatcher_iot_rule:iot_rule":
    return resource_names.iot_rule_name(config, logical_name)

  if template_id in {
    "core:l3_cold:cold_s3_bucket:s3_bucket",
    "core:l3_archive:archive_s3_bucket:s3_bucket",
    "core:l4:twinmaker_s3_bucket:s3_bucket",
  }:
    return resource_names.s3_bucket_name(config, logical_name)

  return resource_names.resource_name(config, logical_name)


def _shared_logical_name(template_id: str) -> str:
  logical_name = SHARED_LOGICAL_NAMES.get(template_id)

  if logical_name is not None:
    return logical_name

  return template_id.split(":")[2]


def _runtime_id(template_id: str, logical_name: str) -> str:
  return runtime_node_id(template_id, logical_name)


def _drafts_by_template_id(
  drafts: Sequence[_RuntimeNodeDraft],
) -> dict[str, list[_RuntimeNodeDraft]]:
  drafts_by_template: dict[str, list[_RuntimeNodeDraft]] = {}

  for draft in drafts:
    drafts_by_template.setdefault(draft.template.id, []).append(draft)

  return drafts_by_template


def _validate_unique_runtime_ids(drafts: Sequence[_RuntimeNodeDraft]) -> None:
  seen_ids: set[str] = set()

  for draft in drafts:
    if draft.id in seen_ids:
      raise ValueError(f"Duplicate runtime dependency node id: {draft.id}")

    seen_ids.add(draft.id)
