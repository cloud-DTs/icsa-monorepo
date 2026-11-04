from deployers.aws.core.dispatcher_iam_role import DispatcherIamRoleDeployer
from deployers.aws.core.dispatcher_iot_rule import DispatcherIotRuleDeployer
from deployers.aws.core.dispatcher_lambda_function import DispatcherLambdaFunctionDeployer
from deployers.aws.core.plan_actions import sort_actions_for_apply
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state

class L1Deployer(Deployer):
  DESTROY_ORDER = {
    "iot_rule": 0,
    "lambda_function": 1,
    "iam": 2,
  }

  DEPLOY_ORDER = {
    "iam": 0,
    "lambda_function": 1,
    "iot_rule": 2,
  }

  def log(self, message):
    print(message)

  def plan(self):
    actions = []
    actions.extend(DispatcherIamRoleDeployer().plan())
    actions.extend(DispatcherLambdaFunctionDeployer().plan())
    actions.extend(DispatcherIotRuleDeployer().plan())
    return {
      "layer": "core_l1",
      "actions": actions,
    }

  def sort_actions_for_apply(self, actions):
    return sort_actions_for_apply(
      actions,
      self.DESTROY_ORDER,
      self.DEPLOY_ORDER,
    )

  def apply(self, layer_plan, action_name):
    layer_name = layer_plan["layer"]
    actions = pending_actions(layer_plan["actions"], action_name)

    if not actions:
      return

    actions = self.sort_actions_for_apply(actions)

    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if resource_type == "iam":
        DispatcherIamRoleDeployer().apply(action, resource)

      elif resource_type == "lambda_function":
        DispatcherLambdaFunctionDeployer().apply(action, resource)

      elif resource_type == "iot_rule":
        DispatcherIotRuleDeployer().apply(action, resource)

      else:
        raise ValueError(
          f"No core_l1 apply handler for {resource_type}/{resource}"
        )

      deployment_state.mark_plan_action_processed("core", layer_name, action)

  def deploy(self):
    DispatcherIamRoleDeployer().deploy()
    DispatcherLambdaFunctionDeployer().deploy()
    DispatcherIotRuleDeployer().deploy()

  def destroy(self):
    DispatcherIotRuleDeployer().destroy()
    DispatcherLambdaFunctionDeployer().destroy()
    DispatcherIamRoleDeployer().destroy()

  def info(self):
    DispatcherIamRoleDeployer().info()
    DispatcherLambdaFunctionDeployer().info()
    DispatcherIotRuleDeployer().info()
