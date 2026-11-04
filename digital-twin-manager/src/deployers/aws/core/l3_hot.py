from deployers.aws.core.hot_cold_mover_event_rule import HotColdMoverEventRuleDeployer
from deployers.aws.core.hot_cold_mover_iam_role import HotColdMoverIamRoleDeployer
from deployers.aws.core.hot_cold_mover_lambda_function import HotColdMoverLambdaFunctionDeployer
from deployers.aws.core.hot_dynamodb_table import HotDynamodbTableDeployer
from deployers.aws.core.hot_reader_iam_role import HotReaderIamRoleDeployer
from deployers.aws.core.hot_reader_lambda_function import HotReaderLambdaFunctionDeployer
from deployers.aws.core.plan_actions import sort_actions_for_apply
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state
import globals

class L3HotDeployer(Deployer):
  def log(self, message):
    print(message)

  DESTROY_ORDER = {
    "eventbridge_rule": 0,
    "lambda_function": 1,
    "iam": 2,
    "dynamodb_table": 3,
  }

  DEPLOY_ORDER = {
    "dynamodb_table": 0,
    "iam": 1,
    "lambda_function": 2,
    "eventbridge_rule": 3,
  }

  def plan(self):
    actions = []
    actions.extend(HotDynamodbTableDeployer().plan())
    actions.extend(HotColdMoverIamRoleDeployer().plan())
    actions.extend(HotColdMoverLambdaFunctionDeployer().plan())
    actions.extend(HotColdMoverEventRuleDeployer().plan())
    actions.extend(HotReaderIamRoleDeployer().plan())
    actions.extend(HotReaderLambdaFunctionDeployer().plan())
    return {
      "layer": "core_l3_hot",
      "actions": actions,
    }

  def sort_actions_for_apply(self, actions):
    return sort_actions_for_apply(
      actions,
      self.DESTROY_ORDER,
      self.DEPLOY_ORDER,
    )

  def _resource_matches(self, resource, previous_resource, desired_resource):
    return resource in [previous_resource, desired_resource]

  def apply(self, layer_plan, action_name):
    layer_name = layer_plan["layer"]
    actions = pending_actions(layer_plan["actions"], action_name)

    if not actions:
      return

    actions = self.sort_actions_for_apply(actions)

    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if (
        resource_type == "dynamodb_table"
        and self._resource_matches(resource, deployment_state.last_applied_hot_dynamodb_table_name(), globals.hot_dynamodb_table_name())
      ):
        HotDynamodbTableDeployer().apply(action, resource)
      elif (
        resource_type == "iam"
        and self._resource_matches(resource, deployment_state.last_applied_hot_cold_mover_iam_role_name(), globals.hot_cold_mover_iam_role_name())
      ):
        HotColdMoverIamRoleDeployer().apply(action, resource)
      elif (
        resource_type == "lambda_function"
        and self._resource_matches(resource, deployment_state.last_applied_hot_cold_mover_lambda_function_name(), globals.hot_cold_mover_lambda_function_name())
      ):
        HotColdMoverLambdaFunctionDeployer().apply(action, resource)
      elif (
        resource_type == "eventbridge_rule"
        and self._resource_matches(resource, deployment_state.last_applied_hot_cold_mover_event_rule_name(), globals.hot_cold_mover_event_rule_name())
      ):
        HotColdMoverEventRuleDeployer().apply(action, resource)
      elif (
        resource_type == "iam"
        and self._resource_matches(resource, deployment_state.last_applied_hot_reader_iam_role_name(), globals.hot_reader_iam_role_name())
      ):
        HotReaderIamRoleDeployer().apply(action, resource)
      elif (
        resource_type == "lambda_function"
        and self._resource_matches(resource, deployment_state.last_applied_hot_reader_lambda_function_name(), globals.hot_reader_lambda_function_name())
      ):
        HotReaderLambdaFunctionDeployer().apply(action, resource)
      else:
        raise ValueError(
          f"No core_l3_hot apply handler for {resource_type}/{resource}"
        )

      deployment_state.mark_plan_action_processed("core", layer_name, action)

  def deploy(self):
    HotDynamodbTableDeployer().deploy()
    HotColdMoverIamRoleDeployer().deploy()
    HotColdMoverLambdaFunctionDeployer().deploy()
    HotColdMoverEventRuleDeployer().deploy()
    HotReaderIamRoleDeployer().deploy()
    HotReaderLambdaFunctionDeployer().deploy()

  def destroy(self):
    HotReaderLambdaFunctionDeployer().destroy()
    HotReaderIamRoleDeployer().destroy()
    HotColdMoverEventRuleDeployer().destroy()
    HotColdMoverLambdaFunctionDeployer().destroy()
    HotColdMoverIamRoleDeployer().destroy()
    HotDynamodbTableDeployer().destroy()

  def info(self):
    HotDynamodbTableDeployer().info()
    HotColdMoverIamRoleDeployer().info()
    HotColdMoverLambdaFunctionDeployer().info()
    HotColdMoverEventRuleDeployer().info()
    HotReaderIamRoleDeployer().info()
    HotReaderLambdaFunctionDeployer().info()
