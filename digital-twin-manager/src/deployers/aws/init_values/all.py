from deployers.aws.init_values.init_values import InitValuesDeployer
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state

class AllDeployer(Deployer):
  def log(self, message):
    print(f"Init Values: {message}")

  def plan(self):
    return {
      "group": "init_values",
      "layers": [{
        "layer": "init_values",
        "actions": InitValuesDeployer().plan()
      }]
    }

  def apply(self, group_plan, action_name):
    layers = group_plan["layers"]

    if len(layers) != 1 or layers[0]["layer"] != "init_values":
      raise ValueError("Invalid init_values plan format. Run 'plan' again.")

    layer_plan = layers[0]
    layer_name = layer_plan["layer"]
    actions = pending_actions(layer_plan["actions"], action_name)

    if not actions:
      return

    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if resource_type != "init_value":
        raise ValueError(
          f"No init_values apply handler for {resource_type}/{resource}"
        )

      InitValuesDeployer().apply(action, resource)
      deployment_state.mark_plan_action_processed("init_values", layer_name, action)

  def deploy(self):
    InitValuesDeployer().deploy()

  def destroy(self):
    InitValuesDeployer().destroy()

  def info(self):
    InitValuesDeployer().info()
