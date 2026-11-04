from deployers.aws.hierarchy.twinmaker_hierarchy import TwinmakerHierarchyDeployer
from deployers.aws.apply_actions import ACTION_DEPLOY, pending_actions
from deployers.base import Deployer
import deployment_state

class AllDeployer(Deployer):
  def log(self, message):
    print(f"Hierarchy: {message}")

  def plan(self):
    return {
      "group": "hierarchy",
      "layers": [{
        "layer": "hierarchy",
        "actions": TwinmakerHierarchyDeployer().plan()
      }]
    }

  def apply(self, group_plan, action_name):
    layers = group_plan["layers"]

    if len(layers) != 1 or layers[0]["layer"] != "hierarchy":
      raise ValueError("Invalid hierarchy plan format. Run 'plan' again.")

    layer_plan = layers[0]
    layer_name = layer_plan["layer"]
    actions = pending_actions(layer_plan["actions"], action_name)

    if not actions:
      return

    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if resource_type != "twinmaker_hierarchy":
        raise ValueError(
          f"No hierarchy apply handler for {resource_type}/{resource}"
        )

      TwinmakerHierarchyDeployer().apply(action, resource)
      deployment_state.mark_plan_action_processed("hierarchy", layer_name, action)

  def validate_plan(self, group_plan):
    for layer in group_plan["layers"]:
      for action in pending_actions(layer["actions"], ACTION_DEPLOY):
        TwinmakerHierarchyDeployer().validate_plan(action)

  def deploy(self):
    TwinmakerHierarchyDeployer().deploy()

  def destroy(self):
    TwinmakerHierarchyDeployer().destroy()

  def info(self):
    TwinmakerHierarchyDeployer().info()
