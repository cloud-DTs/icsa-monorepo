from deployers.aws.core.twinmaker_iam_role import TwinmakerIamRoleDeployer
from deployers.aws.core.twinmaker_s3_bucket import TwinmakerS3BucketDeployer
from deployers.aws.core.twinmaker_workspace import TwinmakerWorkspaceDeployer
from deployers.aws.core.plan_actions import sort_actions_for_apply
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state
import globals

class L4Deployer(Deployer):
  DESTROY_ORDER = {
    "twinmaker_workspace": 0,
    "iam": 1,
    "s3_bucket": 2,
  }

  DEPLOY_ORDER = {
    "s3_bucket": 0,
    "iam": 1,
    "twinmaker_workspace": 2,
  }

  def log(self, message):
    print(message)

  def plan(self):
    actions = []
    actions.extend(TwinmakerS3BucketDeployer().plan())
    actions.extend(TwinmakerIamRoleDeployer().plan())
    actions.extend(TwinmakerWorkspaceDeployer().plan())
    return {
      "layer": "core_l4",
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
        and self._resource_matches(resource, deployment_state.last_applied_twinmaker_s3_bucket_name(), globals.twinmaker_s3_bucket_name())
      ):
        TwinmakerS3BucketDeployer().apply(action, resource)
      elif (
        resource_type == "iam"
        and self._resource_matches(resource, deployment_state.last_applied_twinmaker_iam_role_name(), globals.twinmaker_iam_role_name())
      ):
        TwinmakerIamRoleDeployer().apply(action, resource)
      elif (
        resource_type == "twinmaker_workspace"
        and self._resource_matches(resource, deployment_state.last_applied_twinmaker_workspace_name(), globals.twinmaker_workspace_name())
      ):
        TwinmakerWorkspaceDeployer().apply(action, resource)
      else:
        raise ValueError(
          f"No core_l4 apply handler for {resource_type}/{resource}"
        )

      deployment_state.mark_plan_action_processed("core", layer_name, action)

  def deploy(self):
    TwinmakerS3BucketDeployer().deploy()
    TwinmakerIamRoleDeployer().deploy()
    TwinmakerWorkspaceDeployer().deploy()

  def destroy(self):
    TwinmakerWorkspaceDeployer().destroy()
    TwinmakerIamRoleDeployer().destroy()
    TwinmakerS3BucketDeployer().destroy()

  def info(self):
    TwinmakerS3BucketDeployer().info()
    TwinmakerIamRoleDeployer().info()
    TwinmakerWorkspaceDeployer().info()
