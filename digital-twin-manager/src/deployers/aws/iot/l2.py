from deployers.aws.core.plan_actions import PlanResourceType, sort_actions_for_apply
from deployers.aws.iot.device_reconciliation import (
  desired_iot_devices,
  previous_iot_devices,
  reconciled_iot_devices,
)
from deployers.aws.iot.processor_iam_role import ProcessorIamRoleDeployer
from deployers.aws.iot.processor_lambda_function import ProcessorLambdaFunctionDeployer
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state
import globals

class L2Deployer(Deployer):
  def log(self, message):
    print(f"IoT: {message}")

  DESTROY_ORDER:dict[PlanResourceType, int] = {
    "lambda_function": 0,
    "iam": 1,
  }

  DEPLOY_ORDER:dict[PlanResourceType, int] = {
    "iam": 0,
    "lambda_function": 1,
  }

  def plan(self):
    actions = []
    for previous_iot_device, desired_iot_device in reconciled_iot_devices():
      actions.extend(ProcessorIamRoleDeployer().plan(previous_iot_device, desired_iot_device))
      actions.extend(ProcessorLambdaFunctionDeployer().plan(previous_iot_device, desired_iot_device))
    return {
      "layer": "iot_l2",
      "actions": actions
    }

  def sort_actions_for_apply(self, actions):
    return sort_actions_for_apply(
      actions,
      self.DESTROY_ORDER,
      self.DEPLOY_ORDER,
    )

  def _iot_device_for_action(self, action, resource_type: PlanResourceType):
    resource = action["resource"]

    if action["action"] == "DESTROY":
      if resource_type == "lambda_function":
        for iot_device in previous_iot_devices():
          if deployment_state.last_applied_processor_lambda_function_name(iot_device) == resource:
            return iot_device
      elif resource_type == "iam":
        for iot_device in previous_iot_devices():
          if deployment_state.last_applied_processor_iam_role_name(iot_device) == resource:
            return iot_device

    if action["action"] in ("DEPLOY", "UPDATE", "NO_CHANGE"):
      if resource_type == "lambda_function":
        for iot_device in desired_iot_devices():
          if globals.processor_lambda_function_name(iot_device) == resource:
            return iot_device
      elif resource_type == "iam":
        for iot_device in desired_iot_devices():
          if globals.processor_iam_role_name(iot_device) == resource:
            return iot_device

    return None

  def apply(self, layer_plan, action_name):
    layer_name = layer_plan["layer"]
    actions = self.sort_actions_for_apply(pending_actions(layer_plan["actions"], action_name))

    if not actions:
      return

    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if resource_type == "lambda_function":
        iot_device = self._iot_device_for_action(action, "lambda_function")

        if iot_device is None:
          raise ValueError(f"No IoT device config found for planned processor Lambda: {resource}")

        ProcessorLambdaFunctionDeployer().apply(action, iot_device, resource)

      elif resource_type == "iam":
        iot_device = self._iot_device_for_action(action, "iam")

        if iot_device is None:
          raise ValueError(f"No IoT device config found for planned processor IAM role: {resource}")

        ProcessorIamRoleDeployer().apply(action, iot_device, resource)

      else:
        raise ValueError(
          f"No iot_l2 apply handler for {resource_type}/{resource}"
        )

      deployment_state.mark_plan_action_processed("iot", layer_name, action)

  def deploy(self):
    for iot_device in desired_iot_devices():
      ProcessorIamRoleDeployer().deploy(iot_device)
      ProcessorLambdaFunctionDeployer().deploy(iot_device)

  def destroy(self):
    for iot_device in desired_iot_devices():
      ProcessorLambdaFunctionDeployer().destroy(iot_device)
      ProcessorIamRoleDeployer().destroy(iot_device)

  def info(self):
    for iot_device in desired_iot_devices():
      ProcessorIamRoleDeployer().info(iot_device)
      ProcessorLambdaFunctionDeployer().info(iot_device)
