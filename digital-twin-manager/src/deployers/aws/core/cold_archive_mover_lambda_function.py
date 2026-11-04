import os

import deployment_state
import globals
from dependency_graph import plan_graph_ids
from deployers.aws.core.managed_lambda_function import ManagedLambdaFunctionDeployer
from deployers.aws.lambda_function import LambdaDefinition


class ColdArchiveMoverLambdaFunctionDeployer(ManagedLambdaFunctionDeployer):
  _function_name = staticmethod(globals.cold_archive_mover_lambda_function_name)
  _previous_function_name = staticmethod(deployment_state.last_applied_cold_archive_mover_lambda_function_name)

  def _lambda_definition(self):
    return LambdaDefinition(
      function_name=globals.cold_archive_mover_lambda_function_name(),
      role_name=globals.cold_archive_mover_iam_role_name(),
      code_path=os.path.join(globals.core_lfs_path, "cold-to-archive-mover"),
      graph_id=plan_graph_ids.COLD_ARCHIVE_MOVER_LAMBDA,
      environment={
        "COLD_STORAGE_SIZE_IN_DAYS": str(globals.config["cold_storage_size_in_days"]),
        "SOURCE_S3_BUCKET_NAME": globals.cold_s3_bucket_name(),
        "TARGET_S3_BUCKET_NAME": globals.archive_s3_bucket_name(),
      },
    )
