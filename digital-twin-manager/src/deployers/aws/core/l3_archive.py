from deployers.aws.core.archive_s3_bucket import ArchiveS3BucketDeployer
from deployers.aws.core.plan_actions import sort_actions_for_apply
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state

class L3ArchiveDeployer(Deployer):
  def log(self, message):
    print(message)

  DESTROY_ORDER = {
    "s3_bucket": 0,
  }

  DEPLOY_ORDER = {
    "s3_bucket": 0,
  }

  def plan(self):
    return {
      "layer": "core_l3_archive",
      "actions": ArchiveS3BucketDeployer().plan(),
    }

  def deploy(self):
    ArchiveS3BucketDeployer().deploy()

  def sort_actions_for_apply(self, actions):
    return sort_actions_for_apply(actions, self.DESTROY_ORDER, self.DEPLOY_ORDER)

  def apply(self, layer_plan, action_name):
    layer_name = layer_plan["layer"]
    actions = pending_actions(layer_plan["actions"], action_name)

    if not actions:
      return

    actions = self.sort_actions_for_apply(actions)

    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if resource_type == "s3_bucket":
        ArchiveS3BucketDeployer().apply(action, resource)
      else:
        raise ValueError(
          f"No core_l3_archive apply handler for {resource_type}/{resource}"
        )

      deployment_state.mark_plan_action_processed("core", layer_name, action)

  def destroy(self):
    ArchiveS3BucketDeployer().destroy()

  def info(self):
    ArchiveS3BucketDeployer().info()
