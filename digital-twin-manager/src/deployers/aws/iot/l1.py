from deployers.aws.iot.iot_thing import IotThingDeployer
from deployers.aws.iot.iot_policy import IotPolicyDeployer
from deployers.aws.iot.device_reconciliation import (
  desired_iot_devices,
  previous_iot_devices,
  reconciled_iot_devices,
)
from deployers.aws.apply_actions import pending_actions
from deployers.aws.core.plan_actions import sort_actions_for_apply
from deployers.base import Deployer
import deployment_state
import globals

class L1Deployer(Deployer):
  DESTROY_ORDER = {"iot_thing": 0, "iot_policy": 1}
  DEPLOY_ORDER = {"iot_policy": 0, "iot_thing": 1}

  def log(self, message):
    print(f"IoT: {message}")

  def plan(self):
    actions = IotPolicyDeployer().plan()
    for previous_iot_device, desired_iot_device in reconciled_iot_devices():
      actions.extend(IotThingDeployer().plan(previous_iot_device, desired_iot_device))
    return {
      "layer": "iot_l1",
      "actions": actions
    }

  def _iot_device_for_action(self, action):
    resource = action["resource"]

    if action["action"] == "DESTROY":
      for iot_device in previous_iot_devices():
        if deployment_state.last_applied_iot_thing_name(iot_device) == resource:
          return iot_device

    if action["action"] in ("DEPLOY", "UPDATE"):
      for iot_device in desired_iot_devices():
        if globals.iot_thing_name(iot_device) == resource:
          return iot_device

    return None

  def validate_plan(self, layer_plan):
    policy_actions = [
      action for action in layer_plan["actions"]
      if action["resource_type"] == "iot_policy" and action["action"] != "DESTROY"
    ]
    if pending_actions(layer_plan["actions"], "DEPLOY") and not policy_actions:
      raise ValueError("Shared IoT policy plan metadata is missing. Run 'plan' again.")
    if len(policy_actions) > 1:
      raise ValueError("The saved plan contains duplicate shared IoT policy actions. Run 'plan' again.")
    for action in policy_actions:
      IotPolicyDeployer().validate_plan(action)

  def apply(self, layer_plan, action_name):
    self.validate_plan(layer_plan)
    layer_name = layer_plan["layer"]
    actions = pending_actions(layer_plan["actions"], action_name)

    if not actions:
      return

    actions = sort_actions_for_apply(actions, self.DESTROY_ORDER, self.DEPLOY_ORDER)
    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if resource_type == "iot_policy":
        IotPolicyDeployer().apply(action, resource)
        deployment_state.mark_plan_action_processed("iot", layer_name, action)
        action["processed"] = True
        continue

      if resource_type != "iot_thing":
        raise ValueError(
          f"No iot_l1 apply handler for {resource_type}/{resource}"
        )

      iot_device = self._iot_device_for_action(action)

      if iot_device is None:
        raise ValueError(f"No IoT device config found for planned IoT thing: {resource}")

      policy_action = next((
        candidate for candidate in layer_plan["actions"]
        if candidate["resource_type"] == "iot_policy" and candidate["action"] != "DESTROY"
      ), None)
      IotThingDeployer().apply(action, iot_device, resource, policy_action=policy_action)
      deployment_state.mark_plan_action_processed("iot", layer_name, action)

  def deploy(self):
    IotPolicyDeployer().deploy()
    for iot_device in desired_iot_devices():
      IotThingDeployer().deploy(iot_device)

  def destroy(self):
    for iot_device in desired_iot_devices():
      IotThingDeployer().destroy(iot_device)
    IotPolicyDeployer().destroy()

  def info(self):
    IotPolicyDeployer().info()
    for iot_device in desired_iot_devices():
      IotThingDeployer().info(iot_device)
