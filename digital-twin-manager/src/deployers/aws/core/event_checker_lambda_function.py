import os
import json

import deployment_state
import globals
from dependency_graph import plan_graph_ids
from deployers.aws.core.managed_lambda_function import ManagedLambdaFunctionDeployer
from deployers.aws.lambda_function import LambdaDefinition
from deployers.aws.core import aws_arns


class EventCheckerLambdaFunctionDeployer(ManagedLambdaFunctionDeployer):
  _function_name = staticmethod(globals.event_checker_lambda_function_name)
  _previous_function_name = staticmethod(deployment_state.last_applied_event_checker_lambda_function_name)

  def _lambda_definition(self):
    return LambdaDefinition(
      function_name=globals.event_checker_lambda_function_name(),
      role_name=globals.event_checker_iam_role_name(),
      code_path=os.path.join(globals.core_lfs_path, "event-checker"),
      graph_id=plan_graph_ids.EVENT_CHECKER_LAMBDA,
      environment={
        "DIGITAL_TWIN_NAME": globals.config["digital_twin_name"],
        "TWINMAKER_WORKSPACE_NAME": globals.twinmaker_workspace_name(),
        "LAMBDA_CHAIN_STEP_FUNCTION_ARN": aws_arns.state_machine_arn(
          globals.lambda_chain_step_function_name(), globals.aws_lambda_client.meta.region_name,
        ),
        "EVENT_FEEDBACK_LAMBDA_FUNCTION_ARN": aws_arns.lambda_function_arn(globals.event_feedback_lambda_function_name()),
        "SSM_REGISTRY_PREFIX": globals.ssm_registry_prefix(),
      },
      timeout=900,
      extra_files={"config_events.json": json.dumps(globals.config_events, ensure_ascii=False, separators=(",", ":"))},
    )
