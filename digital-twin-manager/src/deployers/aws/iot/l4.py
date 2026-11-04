from deployers.aws.iot.device_reconciliation import (
  desired_iot_devices,
  previous_iot_devices,
)
from deployers.aws.iot.twinmaker_component_type import TwinmakerComponentTypeDeployer
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state
import globals
from validation import component_types

class L4Deployer(Deployer):
  def log(self, message):
    print(f"IoT: {message}")

  def _group_by_component_type(self, iot_devices, component_type_id_fn):
    groups = {}
    order = []

    for iot_device in iot_devices:
      component_type_id = component_type_id_fn(iot_device)
      groups.setdefault(component_type_id, []).append(iot_device)

      if component_type_id not in order:
        order.append(component_type_id)

    return order, groups

  def plan(self):
    component_types.validate(globals.config, globals.config_iot_devices, globals.config_hierarchy)
    previous_order, previous_groups = self._group_by_component_type(
      previous_iot_devices(),
      deployment_state.last_applied_twinmaker_component_type_id,
    )
    desired_order, desired_groups = self._group_by_component_type(
      desired_iot_devices(),
      globals.twinmaker_component_type_id,
    )

    component_type_ids = previous_order + [
      component_type_id
      for component_type_id in desired_order
      if component_type_id not in previous_groups
    ]

    actions = []

    for component_type_id in component_type_ids:
      previous_group = previous_groups.get(component_type_id)
      desired_group = desired_groups.get(component_type_id)

      actions.extend(
        TwinmakerComponentTypeDeployer().plan(
          previous_group[0] if previous_group else None,
          desired_group[0] if desired_group else None,
        )
      )

    return {
      "layer": "iot_l4",
      "actions": actions
    }

  def _iot_device_for_action(self, action):
    resource = action["resource"]

    if action["action"] == "DESTROY":
      for iot_device in previous_iot_devices():
        if deployment_state.last_applied_twinmaker_component_type_id(iot_device) == resource:
          return iot_device

    if action["action"] == "DEPLOY":
      for iot_device in desired_iot_devices():
        if globals.twinmaker_component_type_id(iot_device) == resource:
          return iot_device

    return None

  def apply(self, layer_plan, action_name):
    component_types.validate(globals.config, globals.config_iot_devices, globals.config_hierarchy)
    layer_name = layer_plan["layer"]
    actions = pending_actions(layer_plan["actions"], action_name)

    if not actions:
      return

    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if resource_type != "twinmaker_component_type":
        raise ValueError(
          f"No iot_l4 apply handler for {resource_type}/{resource}"
        )

      iot_device = self._iot_device_for_action(action)

      if iot_device is None:
        raise ValueError(
          f"No IoT device config found for planned TwinMaker component type: {resource}"
        )

      TwinmakerComponentTypeDeployer().apply(action, iot_device, resource)
      deployment_state.mark_plan_action_processed("iot", layer_name, action)

  def deploy(self):
    component_types.validate(globals.config, globals.config_iot_devices, globals.config_hierarchy)
    _, groups = self._group_by_component_type(
      desired_iot_devices(), globals.twinmaker_component_type_id
    )
    for iot_devices in groups.values():
      TwinmakerComponentTypeDeployer().deploy(iot_devices[0])

  def destroy(self):
    _, groups = self._group_by_component_type(
      desired_iot_devices(), globals.twinmaker_component_type_id
    )
    for iot_devices in groups.values():
      TwinmakerComponentTypeDeployer().destroy(iot_devices[0])

  def info(self):
    _, groups = self._group_by_component_type(
      desired_iot_devices(), globals.twinmaker_component_type_id
    )
    for iot_devices in groups.values():
      TwinmakerComponentTypeDeployer().info(iot_devices[0])
