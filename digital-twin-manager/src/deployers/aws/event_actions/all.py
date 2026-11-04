from deployers.aws.event_actions.lambda_actions import LambdaActionsDeployer
from deployers.aws.apply_actions import pending_actions
from deployers.aws.lambda_function import needs_lambda_validation
from deployers.base import Deployer
import deployment_state

class AllDeployer(Deployer):
  def log(self, message):
    print(f"Event Actions: {message}")

  def plan(self):
    return {
      "group": "event_actions",
      "layers": [{
        "layer": "event_actions",
        "actions": LambdaActionsDeployer().plan()
      }]
    }

  def validate_plan(self, group_plan):
    for layer in group_plan["layers"]:
      deployer = LambdaActionsDeployer()
      replacement_names = deployer.replacement_function_names(layer["actions"])
      for action in layer["actions"]:
        if action["resource_type"] == "event_action" and needs_lambda_validation(action):
          deployer.validate_plan(action, replacement_names)

  def apply(self, group_plan, action_name):
    layers = group_plan["layers"]

    if len(layers) != 1 or layers[0]["layer"] != "event_actions":
      raise ValueError("Invalid event_actions plan format. Run 'plan' again.")

    layer_plan = layers[0]
    layer_name = layer_plan["layer"]
    actions = pending_actions(layer_plan["actions"], action_name)

    if not actions:
      return

    for action in actions:
      resource_type = action["resource_type"]
      resource = action["resource"]

      if resource_type != "event_action":
        raise ValueError(
          f"No event_actions apply handler for {resource_type}/{resource}"
        )

      LambdaActionsDeployer().apply(action, resource)
      deployment_state.mark_plan_action_processed("event_actions", layer_name, action)

  def deploy(self):
    LambdaActionsDeployer().deploy()

  def destroy(self):
    LambdaActionsDeployer().destroy()

  def info(self):
    LambdaActionsDeployer().info()
