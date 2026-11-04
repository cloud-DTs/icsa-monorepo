import os
import json

import deployment_state
import globals
from dependency_graph import plan_graph_ids
from deployers.aws.core.managed_lambda_function import ManagedLambdaFunctionDeployer
from deployers.aws.lambda_function import LambdaDefinition


def _iot_device_ids(iot_devices):
  return sorted(iot_device["id"] for iot_device in iot_devices)


class HotColdMoverLambdaFunctionDeployer(ManagedLambdaFunctionDeployer):
  _function_name = staticmethod(globals.hot_cold_mover_lambda_function_name)
  _previous_function_name = staticmethod(deployment_state.last_applied_hot_cold_mover_lambda_function_name)

  def _lambda_definition(self):
    return LambdaDefinition(
      function_name=globals.hot_cold_mover_lambda_function_name(),
      role_name=globals.hot_cold_mover_iam_role_name(),
      code_path=os.path.join(globals.core_lfs_path, "hot-to-cold-mover"),
      graph_id=plan_graph_ids.HOT_COLD_MOVER_LAMBDA,
      environment={
        "HOT_STORAGE_SIZE_IN_DAYS": str(globals.config["hot_storage_size_in_days"]),
        "DYNAMODB_TABLE_NAME": globals.hot_dynamodb_table_name(),
        "S3_BUCKET_NAME": globals.cold_s3_bucket_name(),
      },
      extra_files={"iot_device_ids.json": json.dumps(_iot_device_ids(globals.config_iot_devices), ensure_ascii=False, separators=(",", ":"))},
    )
