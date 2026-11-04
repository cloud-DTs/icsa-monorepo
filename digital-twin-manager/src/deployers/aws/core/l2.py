from deployers.aws.core.event_checker_iam_role import EventCheckerIamRoleDeployer
from deployers.aws.core.event_checker_lambda_function import EventCheckerLambdaFunctionDeployer
from deployers.aws.core.event_feedback_iam_role import EventFeedbackIamRoleDeployer
from deployers.aws.core.event_feedback_lambda_function import EventFeedbackLambdaFunctionDeployer
from deployers.aws.core.lambda_chain_iam_role import LambdaChainIamRoleDeployer
from deployers.aws.core.lambda_chain_step_function import LambdaChainStepFunctionDeployer
from deployers.aws.core.persister_iam_role import PersisterIamRoleDeployer
from deployers.aws.core.persister_lambda_function import PersisterLambdaFunctionDeployer
from deployers.aws.core.plan_actions import sort_actions_for_apply
from deployers.aws.apply_actions import pending_actions
from deployers.base import Deployer
import deployment_state
import globals

class L2Deployer(Deployer):
  def log(self, message):
    print(message)

  DESTROY_ORDER = {
    "lambda_function": 0,
    "step_function": 1,
    "iam": 2,
  }

  DEPLOY_ORDER = {
    "iam": 0,
    "lambda_function": 1,
    "step_function": 2,
  }

  def plan(self):
    actions = []
    actions.extend(PersisterIamRoleDeployer().plan())
    actions.extend(PersisterLambdaFunctionDeployer().plan())
    actions.extend(EventFeedbackIamRoleDeployer().plan())
    actions.extend(EventFeedbackLambdaFunctionDeployer().plan())
    actions.extend(EventCheckerIamRoleDeployer().plan())
    actions.extend(EventCheckerLambdaFunctionDeployer().plan())
    actions.extend(LambdaChainIamRoleDeployer().plan())
    actions.extend(LambdaChainStepFunctionDeployer().plan())
    return {
      "layer": "core_l2",
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
        resource_type == "iam"
        and self._resource_matches(resource, deployment_state.last_applied_persister_iam_role_name(), globals.persister_iam_role_name())
      ):
        PersisterIamRoleDeployer().apply(action, resource)
      elif (
        resource_type == "lambda_function"
        and self._resource_matches(resource, deployment_state.last_applied_persister_lambda_function_name(), globals.persister_lambda_function_name())
      ):
        PersisterLambdaFunctionDeployer().apply(action, resource)
      elif (
        resource_type == "iam"
        and self._resource_matches(resource, deployment_state.last_applied_event_feedback_iam_role_name(), globals.event_feedback_iam_role_name())
      ):
        EventFeedbackIamRoleDeployer().apply(action, resource)
      elif (
        resource_type == "lambda_function"
        and self._resource_matches(resource, deployment_state.last_applied_event_feedback_lambda_function_name(), globals.event_feedback_lambda_function_name())
      ):
        EventFeedbackLambdaFunctionDeployer().apply(action, resource)
      elif (
        resource_type == "iam"
        and self._resource_matches(resource, deployment_state.last_applied_event_checker_iam_role_name(), globals.event_checker_iam_role_name())
      ):
        EventCheckerIamRoleDeployer().apply(action, resource)
      elif (
        resource_type == "lambda_function"
        and self._resource_matches(resource, deployment_state.last_applied_event_checker_lambda_function_name(), globals.event_checker_lambda_function_name())
      ):
        EventCheckerLambdaFunctionDeployer().apply(action, resource)
      elif (
        resource_type == "iam"
        and self._resource_matches(resource, deployment_state.last_applied_lambda_chain_iam_role_name(), globals.lambda_chain_iam_role_name())
      ):
        LambdaChainIamRoleDeployer().apply(action, resource)
      elif (
        resource_type == "step_function"
        and self._resource_matches(resource, deployment_state.last_applied_lambda_chain_step_function_name(), globals.lambda_chain_step_function_name())
      ):
        LambdaChainStepFunctionDeployer().apply(action, resource)
      else:
        raise ValueError(
          f"No core_l2 apply handler for {resource_type}/{resource}"
        )

      deployment_state.mark_plan_action_processed("core", layer_name, action)

  def deploy(self):
    PersisterIamRoleDeployer().deploy()
    PersisterLambdaFunctionDeployer().deploy()
    EventFeedbackIamRoleDeployer().deploy()
    EventFeedbackLambdaFunctionDeployer().deploy()
    EventCheckerIamRoleDeployer().deploy()
    EventCheckerLambdaFunctionDeployer().deploy()
    LambdaChainIamRoleDeployer().deploy()
    LambdaChainStepFunctionDeployer().deploy()

  def destroy(self):
    LambdaChainStepFunctionDeployer().destroy()
    LambdaChainIamRoleDeployer().destroy()
    EventCheckerLambdaFunctionDeployer().destroy()
    EventCheckerIamRoleDeployer().destroy()
    EventFeedbackLambdaFunctionDeployer().destroy()
    EventFeedbackIamRoleDeployer().destroy()
    PersisterLambdaFunctionDeployer().destroy()
    PersisterIamRoleDeployer().destroy()

  def info(self):
    PersisterIamRoleDeployer().info()
    PersisterLambdaFunctionDeployer().info()
    EventFeedbackIamRoleDeployer().info()
    EventFeedbackLambdaFunctionDeployer().info()
    EventCheckerIamRoleDeployer().info()
    EventCheckerLambdaFunctionDeployer().info()
    LambdaChainIamRoleDeployer().info()
    LambdaChainStepFunctionDeployer().info()
