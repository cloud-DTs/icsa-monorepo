import deployment_state
import resource_names
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE
from deployers.aws.core.json_helpers import content_changed
from deployers.aws.iot.device_config import (
  effective_iot_devices, infer_iot_device_id, iot_device_ids_by_component_type,
)
from deployers.aws.core.plan_actions import plan_action
from deployers.base import Deployer
from dependency_graph import plan_graph_ids
import time
import globals
import util
from botocore.exceptions import ClientError

DELETE_POLL_SECONDS = 2
DELETE_PROGRESS_LOG_SECONDS = 30
DELETE_TIMEOUT_SECONDS = 60
UPDATE_POLL_SECONDS = 2
UPDATE_TIMEOUT_SECONDS = 60


class TwinmakerHierarchyDeployer(Deployer):
  def log(self, message):
    print(f"Hierarchy: {message}")

  def _root_entities_by_id(self, hierarchy):
    return {entity["id"]: entity for entity in hierarchy}

  def _ordered_root_ids(self, previous_hierarchy, desired_hierarchy):
    previous_entities = self._root_entities_by_id(previous_hierarchy)
    root_ids = []

    for entity in previous_hierarchy:
      root_ids.append(entity["id"])

    for entity in desired_hierarchy:
      if entity["id"] not in previous_entities:
        root_ids.append(entity["id"])

    return root_ids


  def _root_entity(self, hierarchy, entity_id):
    entity = self._root_entities_by_id(hierarchy).get(entity_id)

    if entity is None:
      raise ValueError(f"TwinMaker Hierarchy root entity not found: {entity_id}")

    return entity

  def _configured_iot_device_ids(self):
    return {
      iot_device["id"]
      for iot_device in effective_iot_devices(globals.config_iot_devices)
    }

  def _inferred_device_bindings(self, hierarchy, device_ids_by_type=None):
    if device_ids_by_type is None:
      device_ids_by_type = iot_device_ids_by_component_type(globals.config, globals.config_iot_devices, hierarchy)
    bindings = []

    def collect(entity):
      for child in entity.get("children", []):
        if child["type"] == "entity":
          collect(child)
        elif "iotDeviceId" not in child:
          component_type_id = resource_names.hierarchy_component_type_id(globals.config, child)
          device_id = infer_iot_device_id(component_type_id, device_ids_by_type)
          if device_id is not None:
            bindings.append({
              "entity_id": entity["id"],
              "component_name": child["name"],
              "component_type_id": component_type_id,
              "iot_device_id": device_id,
            })

    for entity in hierarchy:
      collect(entity)
    return bindings

  def _binding_components(self, entity, component_names):
    components = entity.get("components", {})
    for name in component_names:
      if name not in components and entity.get("areAllComponentsReturned") is False:
        raise ValueError(f"AWS returned incomplete components for TwinMaker entity {entity['entityId']}.")
      component = components.get(name, {})
      if (
        "iotDeviceId" not in component.get("properties", {})
        and component.get("areAllPropertiesReturned") is False
      ):
        raise ValueError(f"AWS returned incomplete properties for TwinMaker component {entity['entityId']}/{name}.")
    return components

  def _binding_snapshot(self, bindings, workspace_name):
    native_types = {}
    entities = {}
    snapshot = []
    for binding in bindings:
      component_type_id = binding["component_type_id"]
      if component_type_id not in native_types:
        component_type = globals.aws_twinmaker_client.get_component_type(
          workspaceId=workspace_name, componentTypeId=component_type_id,
        )
        native_types[component_type_id] = "iotDeviceId" in component_type.get("propertyDefinitions", {})
      if not native_types[component_type_id]:
        continue
      entity_id = binding["entity_id"]
      if entity_id not in entities:
        entities[entity_id] = globals.aws_twinmaker_client.get_entity(
          workspaceId=workspace_name, entityId=entity_id,
        )
      entity = entities[entity_id]
      components = self._binding_components(entity, [binding["component_name"]])
      component = components.get(binding["component_name"], {})
      if component.get("componentTypeId") != component_type_id:
        raise ValueError(
          f"TwinMaker component {entity_id}/{binding['component_name']} changed in AWS. "
          "Check its Component Type and run 'plan' again."
        )
      if (
        entity.get("status", {}).get("state", "ACTIVE") != "ACTIVE"
        or component.get("status", {}).get("state", "ACTIVE") != "ACTIVE"
      ):
        raise ValueError(f"TwinMaker component {entity_id}/{binding['component_name']} is not active.")
      device_property = component.get("properties", {}).get("iotDeviceId", {})
      snapshot.append({**binding, "aws_value": device_property.get("value")})
    return snapshot

  def validate_plan(self, action):
    if "component_device_bindings" not in action:
      raise ValueError("TwinMaker device binding metadata is missing. Run 'plan' again.")
    entity = self._root_entity(globals.config_hierarchy, action["resource"])
    device_ids_by_type = iot_device_ids_by_component_type(
      globals.config, globals.config_iot_devices, globals.config_hierarchy,
    )
    bindings = self._inferred_device_bindings([entity], device_ids_by_type)
    if action["action"] == ACTION_DEPLOY:
      if bindings != action["component_device_bindings"]:
        raise ValueError("TwinMaker device bindings changed after planning. Run 'plan' again.")
      return
    snapshot = self._binding_snapshot(bindings, globals.twinmaker_workspace_name())
    if not snapshot or snapshot != action["component_device_bindings"]:
      raise ValueError("TwinMaker device bindings changed after planning. Run 'plan' again.")

  def _update_device_bindings(self, action):
    self.validate_plan(action)
    workspace_name = globals.twinmaker_workspace_name()
    updates_by_entity = {}
    for binding in action["component_device_bindings"]:
      value = {"stringValue": binding["iot_device_id"]}
      if binding["aws_value"] == value:
        continue
      updates_by_entity.setdefault(binding["entity_id"], {})[binding["component_name"]] = {
        "updateType": "UPDATE",
        "propertyUpdates": {"iotDeviceId": {"updateType": "UPDATE", "value": value}},
      }
    for entity_id, updates in updates_by_entity.items():
      globals.aws_twinmaker_client.update_entity(
        workspaceId=workspace_name, entityId=entity_id, componentUpdates=updates,
      )
      deadline = time.monotonic() + UPDATE_TIMEOUT_SECONDS
      while True:
        entity = globals.aws_twinmaker_client.get_entity(workspaceId=workspace_name, entityId=entity_id)
        components = self._binding_components(entity, updates)
        states = [entity.get("status", {}).get("state", "ACTIVE")] + [
          components.get(name, {}).get("status", {}).get("state", "ACTIVE") for name in updates
        ]
        if "ERROR" in states:
          raise ValueError(f"TwinMaker entity {entity_id} failed to update its device bindings.")
        if all(state == "ACTIVE" for state in states) and all(
          components.get(name, {}).get("properties", {}).get("iotDeviceId", {}).get("value")
          == update["propertyUpdates"]["iotDeviceId"]["value"]
          for name, update in updates.items()
        ):
          break
        if time.monotonic() >= deadline:
          raise TimeoutError(f"Timed out waiting for TwinMaker entity {entity_id} device bindings.")
        time.sleep(UPDATE_POLL_SECONDS)
      self.log(f"Updated IoT device bindings on TwinMaker Entity: {entity_id}")

  def _collect_missing_iot_device_ids_for_components(
    self,
    entity_info,
    configured_iot_device_ids,
    missing_iot_device_ids,
  ):
    for child in entity_info.get("children", []):
      if child["type"] == "entity":
        self._collect_missing_iot_device_ids_for_components(
          child,
          configured_iot_device_ids,
          missing_iot_device_ids,
        )
      elif child["type"] == "component" and "iotDeviceId" in child:
        iot_device_id = child["iotDeviceId"]

        if iot_device_id not in configured_iot_device_ids:
          missing_iot_device_ids.add(iot_device_id)

  def _validate_component_type_sources(self, hierarchy):
    configured_iot_device_ids = self._configured_iot_device_ids()
    missing_iot_device_ids = set()

    for entity in hierarchy:
      self._collect_missing_iot_device_ids_for_components(
        entity,
        configured_iot_device_ids,
        missing_iot_device_ids,
      )

    if missing_iot_device_ids:
      missing_ids = ", ".join(sorted(missing_iot_device_ids))
      raise ValueError(
        "Hierarchy references IoT device id(s) that are missing from "
        f"config_iot_devices.json: {missing_ids}. "
        "TwinMaker component types are deployed from config_iot_devices before "
        "hierarchy is applied."
      )

    self._inferred_device_bindings(hierarchy)

  def _wait_until_entity_deleted(self, workspace_name, entity):
    started_at = time.monotonic()
    last_log_at = started_at

    while True:
      try:
        response = globals.aws_twinmaker_client.get_entity(workspaceId=workspace_name, entityId=entity["id"])
        elapsed_seconds = int(time.monotonic() - started_at)

        if elapsed_seconds >= DELETE_TIMEOUT_SECONDS:
          status = response.get("status", {})
          state = status.get("state", "UNKNOWN")
          error_message = status.get("error", {}).get("message")
          details = f" Current state: {state}."

          if error_message:
            details += f" Error: {error_message}"

          # raise TimeoutError(
          #   f"Timed out waiting for IoT TwinMaker Entity deletion: {entity["id"]}."
          #   f"{details}"
          # )
          self.log(f"Timed out waiting for IoT TwinMaker Entity deletion: {entity["id"]}. Details: {details}. Continue execution.")
          break

        now = time.monotonic()

        if now - last_log_at >= DELETE_PROGRESS_LOG_SECONDS:
          state = response.get("status", {}).get("state", "UNKNOWN")
          self.log(
            f"Still waiting for IoT TwinMaker Entity deletion: {entity["id"]} "
            f"({elapsed_seconds}s, state: {state})"
          )
          last_log_at = now

        time.sleep(DELETE_POLL_SECONDS)
      except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
          break
        else:
          raise

    self.log(f"Deleted IoT TwinMaker Entity: {entity["id"]}")

  def _deploy_twinmaker_entity(
    self, entity_info, workspace_name, parent_info=None, device_ids_by_type=None,
  ):
    create_entity_params = {
      "workspaceId": workspace_name,
      "entityName": entity_info.get("name") or entity_info["id"],
      "entityId": entity_info["id"],
    }

    if parent_info is not None:
      create_entity_params["parentEntityId"] = parent_info["id"]

    response = globals.aws_twinmaker_client.create_entity(**create_entity_params)

    self.log(f"Created IoT TwinMaker Entity: {response["entityId"]}")

    for child in entity_info["children"]:
      if child["type"] == "entity":
        self._deploy_twinmaker_entity(child, workspace_name, entity_info, device_ids_by_type)
      elif child["type"] == "component":
        self._deploy_twinmaker_component(child, entity_info, workspace_name, device_ids_by_type)

  def _deploy_twinmaker_component(
    self, component_info, parent_info, workspace_name, device_ids_by_type=None,
  ):
    component_type_id = resource_names.hierarchy_component_type_id(
      globals.config,
      component_info,
    )

    component_update = {
      "updateType": "CREATE",
      "componentTypeId": component_type_id,
    }

    device_id = component_info.get("iotDeviceId")
    if device_id is None:
      if device_ids_by_type is None:
        device_ids_by_type = iot_device_ids_by_component_type(
          globals.config, globals.config_iot_devices, globals.config_hierarchy,
        )
      device_id = infer_iot_device_id(component_type_id, device_ids_by_type)
      if device_id is not None:
        component_type = globals.aws_twinmaker_client.get_component_type(
          workspaceId=workspace_name, componentTypeId=component_type_id,
        )
        if "iotDeviceId" not in component_type.get("propertyDefinitions", {}):
          device_id = None

    if device_id is not None:
      component_update["propertyUpdates"] = {
        "iotDeviceId": {
          "updateType": "CREATE",
          "value": {"stringValue": str(device_id)},
        }
      }

    globals.aws_twinmaker_client.update_entity(
      workspaceId=workspace_name,
      entityId=parent_info["id"],
      componentUpdates={
          component_info["name"]: component_update
      }
    )

    self.log(f"Created IoT TwinMaker Component: {component_info["name"]}")

  def plan(self):
    previous_hierarchy = deployment_state.last_applied_config_hierarchy
    desired_hierarchy = globals.config_hierarchy
    device_ids_by_type = iot_device_ids_by_component_type(globals.config, globals.config_iot_devices, desired_hierarchy)
    self._inferred_device_bindings(desired_hierarchy, device_ids_by_type)

    previous_workspace_name = deployment_state.last_applied_twinmaker_workspace_name()
    desired_workspace_name = globals.twinmaker_workspace_name()

    previous_entities = self._root_entities_by_id(previous_hierarchy)
    desired_entities = self._root_entities_by_id(desired_hierarchy)
    actions = []

    for entity_id in self._ordered_root_ids(previous_hierarchy, desired_hierarchy):
      previous_entity = previous_entities.get(entity_id)
      desired_entity = desired_entities.get(entity_id)
      bindings = (
        self._inferred_device_bindings([desired_entity], device_ids_by_type)
        if desired_entity is not None else []
      )

      if previous_entity is None:
        self.log(f"TwinMaker Hierarchy root entity {entity_id} is new.")
        actions.append(
          plan_action(
            entity_id,
            "twinmaker_hierarchy",
            action="DEPLOY",
            graph_id=plan_graph_ids.twinmaker_hierarchy(entity_id),
            component_device_bindings=bindings,
          )
        )
        continue

      if desired_entity is None:
        self.log(f"TwinMaker Hierarchy root entity {entity_id} was removed from config.")
        actions.append(
          plan_action(
            entity_id,
            "twinmaker_hierarchy",
            action="DESTROY",
            graph_id=plan_graph_ids.twinmaker_hierarchy(entity_id),
          )
        )
        continue

      if (
        previous_workspace_name == desired_workspace_name
        and not content_changed(previous_entity, desired_entity)
      ):
        snapshot = self._binding_snapshot(bindings, desired_workspace_name)
        if any(binding["aws_value"] != {"stringValue": binding["iot_device_id"]} for binding in snapshot):
          self.log(f"TwinMaker Hierarchy root entity {entity_id} needs IoT device bindings.")
          actions.append(plan_action(
            entity_id, "twinmaker_hierarchy", action=ACTION_UPDATE,
            graph_id=plan_graph_ids.twinmaker_hierarchy(entity_id),
            component_device_bindings=snapshot,
          ))
          continue
        self.log(f"TwinMaker Hierarchy root entity {entity_id} is up to date.")
        actions.append(
          plan_action(
            entity_id,
            "twinmaker_hierarchy",
            graph_id=plan_graph_ids.twinmaker_hierarchy(entity_id),
          )
        )
        continue

      if previous_workspace_name != desired_workspace_name:
        self.log(
          "TwinMaker Hierarchy workspace has changed from "
          f"{previous_workspace_name} to {desired_workspace_name}."
        )

      if content_changed(previous_entity, desired_entity):
        self.log(f"TwinMaker Hierarchy root entity {entity_id} has changed.")

      actions.extend([
        plan_action(
          entity_id,
          "twinmaker_hierarchy",
          action="DESTROY",
          graph_id=plan_graph_ids.twinmaker_hierarchy(entity_id),
        ),
        plan_action(
          entity_id,
          "twinmaker_hierarchy",
          action="DEPLOY",
          graph_id=plan_graph_ids.twinmaker_hierarchy(entity_id),
          component_device_bindings=bindings,
        ),
      ])

    return actions


  def deploy(self, entity_id=None, hierarchy=None, workspace_name=None):
    if hierarchy is None:
      hierarchy = globals.config_hierarchy

    workspace_name = workspace_name or globals.twinmaker_workspace_name()
    self._validate_component_type_sources(hierarchy)
    device_ids_by_type = iot_device_ids_by_component_type(globals.config, globals.config_iot_devices, hierarchy)

    if entity_id is not None:
      self._deploy_twinmaker_entity(
        self._root_entity(hierarchy, entity_id),
        workspace_name,
        device_ids_by_type=device_ids_by_type,
      )
      return

    for entity in hierarchy:
      self._deploy_twinmaker_entity(entity, workspace_name, device_ids_by_type=device_ids_by_type)

  def destroy(self, entity_id=None, hierarchy=None, workspace_name=None):
    if hierarchy is None:
      hierarchy = globals.config_hierarchy

    workspace_name = workspace_name or globals.twinmaker_workspace_name()

    if entity_id is not None:
      hierarchy = [self._root_entity(hierarchy, entity_id)]

    deleting_entities = []

    for entity in hierarchy:
      try:
        globals.aws_twinmaker_client.delete_entity(workspaceId=workspace_name, entityId=entity["id"], isRecursive=True)
        deleting_entities.append(entity)
      except ClientError as e:
        error = e.response["Error"]

        if error["Code"] == "ResourceNotFoundException":
          continue

        if error["Code"] == "ValidationException" and "already in Deleting state" in error["Message"]:
          self.log(f"IoT TwinMaker Entity deletion already in progress: {entity["id"]}")
          deleting_entities.append(entity)
          continue

        raise

    for entity in deleting_entities:
      self._wait_until_entity_deleted(workspace_name, entity)

  def apply(self, action, resource):
    if action["action"] in (ACTION_DEPLOY, ACTION_UPDATE) and resource != action.get("resource"):
      raise ValueError("TwinMaker entity does not match the planned resource. Run 'plan' again.")
    if action["action"] == ACTION_DESTROY:
      self.destroy(
        entity_id=resource,
        hierarchy=deployment_state.last_applied_config_hierarchy,
        workspace_name=deployment_state.last_applied_twinmaker_workspace_name(),
      )
    elif action["action"] == ACTION_DEPLOY:
      self.validate_plan(action)
      self.deploy(
        entity_id=resource,
        hierarchy=globals.config_hierarchy,
        workspace_name=globals.twinmaker_workspace_name(),
      )
    elif action["action"] == ACTION_UPDATE:
      self._update_device_bindings(action)
    else:
      raise ValueError(f"Unsupported hierarchy action: {action['action']}")


  def info(self, hierarchy=None, parent=None):
    workspace_name = globals.twinmaker_workspace_name()

    if hierarchy is None:
      hierarchy = globals.config_hierarchy

    for entry in hierarchy:
      if entry["type"] == "entity":
        try:
          response = globals.aws_twinmaker_client.get_entity(workspaceId=workspace_name, entityId=entry["id"])
          self.log(f"✅ IoT TwinMaker Entity exists: {util.link_to_twinmaker_entity(workspace_name, entry["id"])}")

          if parent is not None and parent["entityId"] != response.get("parentEntityId"):
            self.log(f"❌ IoT TwinMaker Entity {entry["id"]} is missing parent: {parent["entityId"]}")

          if "children" in entry:
            self.info(entry["children"], response)
        except ClientError as e:
          if e.response["Error"]["Code"] == "ResourceNotFoundException":
            self.log(f"❌ IoT TwinMaker Entity missing: {entry["id"]}")
          else:
            raise

      elif entry["type"] == "component":
        if parent is None:
          continue

        if entry["name"] not in parent.get("components", {}):
          self.log(f"❌ IoT TwinMaker Entity {parent["entityId"]} is missing component: {entry["name"]}")
          continue

        self.log(f"✅ IoT TwinMaker Component exists: {util.link_to_twinmaker_component(workspace_name, parent["entityId"], entry["name"])}")

        component_info = parent["components"][entry["name"]]

        entry_component_type_id = resource_names.hierarchy_component_type_id(
          globals.config,
          entry,
        )

        if component_info["componentTypeId"] != entry_component_type_id:
          self.log(f"❌ IoT TwinMaker Component {entry["name"]} has the wrong component type: {component_info["componentTypeId"]}")
