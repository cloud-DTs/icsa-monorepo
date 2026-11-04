import os

import deployment_state
import globals
from dependency_graph import plan_graph_ids
from deployers.aws.core.managed_lambda_function import ManagedLambdaFunctionDeployer
from deployers.aws.lambda_function import LambdaDefinition


class EventFeedbackLambdaFunctionDeployer(ManagedLambdaFunctionDeployer):
  _function_name = staticmethod(globals.event_feedback_lambda_function_name)
  _previous_function_name = staticmethod(deployment_state.last_applied_event_feedback_lambda_function_name)

  def _lambda_definition(self):
    return LambdaDefinition(
      function_name=globals.event_feedback_lambda_function_name(),
      role_name=globals.event_feedback_iam_role_name(),
      code_path=os.path.join(globals.core_lfs_path, "event-feedback"),
      graph_id=plan_graph_ids.EVENT_FEEDBACK_LAMBDA,
      environment={"DIGITAL_TWIN_NAME": globals.config["digital_twin_name"]},
    )
