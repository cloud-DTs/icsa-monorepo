import os

import deployment_state
import globals
from dependency_graph import plan_graph_ids
from deployers.aws.core.managed_lambda_function import ManagedLambdaFunctionDeployer
from deployers.aws.lambda_function import LambdaDefinition


class PersisterLambdaFunctionDeployer(ManagedLambdaFunctionDeployer):
  _function_name = staticmethod(globals.persister_lambda_function_name)
  _previous_function_name = staticmethod(deployment_state.last_applied_persister_lambda_function_name)

  def _lambda_definition(self):
    return LambdaDefinition(
      function_name=globals.persister_lambda_function_name(),
      role_name=globals.persister_iam_role_name(),
      code_path=os.path.join(globals.core_lfs_path, "persister"),
      graph_id=plan_graph_ids.PERSISTER_LAMBDA,
      environment={
        "DEBUG": str(globals.debug),
        "DYNAMODB_TABLE_NAME": globals.hot_dynamodb_table_name(),
        "EVENT_CHECKER_LAMBDA_NAME": globals.event_checker_lambda_function_name(),
      },
    )
