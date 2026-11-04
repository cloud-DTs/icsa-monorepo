from deployers.aws.core.cold_archive_mover_event_rule import ColdArchiveMoverEventRuleDeployer
from deployers.aws.core.cold_archive_mover_iam_role import ColdArchiveMoverIamRoleDeployer
from deployers.aws.core.cold_archive_mover_lambda_function import ColdArchiveMoverLambdaFunctionDeployer
from deployers.aws.core.cold_s3_bucket import ColdS3BucketDeployer
from deployers.aws.core.plan_actions import sort_actions_for_apply
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state
import globals

class L3ColdDeployer(Deployer):
  def log(self, message):
    print(message)

  DESTROY_ORDER = {
    "eventbridge_rule": 0,
    "lambda_function": 1,
    "iam": 2,
    "s3_bucket": 3,
  }

  DEPLOY_ORDER = {
    "s3_bucket": 0,
    "iam": 1,
    "lambda_function": 2,
    "eventbridge_rule": 3,
  }

  def plan(self):
    actions = []
    actions.extend(ColdS3BucketDeployer().plan())
    actions.extend(ColdArchiveMoverIamRoleDeployer().plan())
    actions.extend(ColdArchiveMoverLambdaFunctionDeployer().plan())
    actions.extend(ColdArchiveMoverEventRuleDeployer().plan())
    return {
      "layer": "core_l3_cold",
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
        resource_type == "s3_bucket"
        and self._resource_matches(resource, deployment_state.last_applied_cold_s3_bucket_name(), globals.cold_s3_bucket_name())
      ):
        ColdS3BucketDeployer().apply(action, resource)
      elif (
        resource_type == "iam"
        and self._resource_matches(resource, deployment_state.last_applied_cold_archive_mover_iam_role_name(), globals.cold_archive_mover_iam_role_name())
      ):
        ColdArchiveMoverIamRoleDeployer().apply(action, resource)
      elif (
        resource_type == "lambda_function"
        and self._resource_matches(resource, deployment_state.last_applied_cold_archive_mover_lambda_function_name(), globals.cold_archive_mover_lambda_function_name())
      ):
        ColdArchiveMoverLambdaFunctionDeployer().apply(action, resource)
      elif (
        resource_type == "eventbridge_rule"
        and self._resource_matches(resource, deployment_state.last_applied_cold_archive_mover_event_rule_name(), globals.cold_archive_mover_event_rule_name())
      ):
        ColdArchiveMoverEventRuleDeployer().apply(action, resource)
      else:
        raise ValueError(
          f"No core_l3_cold apply handler for {resource_type}/{resource}"
        )

      deployment_state.mark_plan_action_processed("core", layer_name, action)

  def deploy(self):
    ColdS3BucketDeployer().deploy()
    ColdArchiveMoverIamRoleDeployer().deploy()
    ColdArchiveMoverLambdaFunctionDeployer().deploy()
    ColdArchiveMoverEventRuleDeployer().deploy()

  def destroy(self):
    ColdArchiveMoverEventRuleDeployer().destroy()
    ColdArchiveMoverLambdaFunctionDeployer().destroy()
    ColdArchiveMoverIamRoleDeployer().destroy()
    ColdS3BucketDeployer().destroy()

  def info(self):
    ColdS3BucketDeployer().info()
    ColdArchiveMoverIamRoleDeployer().info()
    ColdArchiveMoverLambdaFunctionDeployer().info()
    ColdArchiveMoverEventRuleDeployer().info()
