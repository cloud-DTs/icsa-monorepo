import os
import zipfile

import deployment_state
import globals
from dependency_graph import plan_graph_ids
from deployers.aws.core.managed_lambda_function import ManagedLambdaFunctionDeployer
from deployers.aws.lambda_function import LambdaDefinition


class HotReaderLambdaFunctionDeployer(ManagedLambdaFunctionDeployer):
  _function_name = staticmethod(globals.hot_reader_lambda_function_name)
  _previous_function_name = staticmethod(deployment_state.last_applied_hot_reader_lambda_function_name)

  def _lambda_definition(self):
    return LambdaDefinition(
      function_name=globals.hot_reader_lambda_function_name(),
      role_name=globals.hot_reader_iam_role_name(),
      code_path=os.path.join(globals.core_lfs_path, "hot-reader"),
      graph_id=plan_graph_ids.HOT_READER_LAMBDA,
      environment={
        "DIGITAL_TWIN_NAME": globals.config["digital_twin_name"],
        "DYNAMODB_TABLE_NAME": globals.hot_dynamodb_table_name(),
      },
      timeout=900,
      compression=zipfile.ZIP_STORED,
      preserve_executable=False,
    )

  def deploy(self, function_name=None, role_name=None, zip_code=None):
    super().deploy(function_name, role_name, zip_code)
    globals.aws_lambda_client.add_permission(
      FunctionName=function_name or self._function_name(),
      StatementId="AllowTwinmakerInvoke",
      Action="lambda:InvokeFunction",
      Principal="iottwinmaker.amazonaws.com",
      SourceAccount=globals.aws_sts_client.get_caller_identity()["Account"],
    )
