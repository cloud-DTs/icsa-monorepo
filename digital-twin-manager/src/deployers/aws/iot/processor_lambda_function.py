import deployment_state
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE
from deployers.aws.core.plan_actions import plan_action
from deployers.base import Deployer
from deployers.aws.lambda_function import (
  LambdaDefinition, create_lambda, plan_lambda, update_lambda, validate_aws_plan, validate_local_plan,
)
from dependency_graph import plan_graph_ids
import globals
import os
from botocore.exceptions import ClientError
import util

class ProcessorLambdaFunctionDeployer(Deployer):
  def log(self, message):
    print(f"IoT: {message}")

  def _lambda_definition(self, iot_device):
    code_path = os.path.join(
      globals.project_path(), globals.processor_lfs_path,
      globals.processor_lambda_function_name_local(iot_device),
    )
    if not os.path.exists(code_path):
      code_path = os.path.join(globals.project_path(), globals.core_lfs_path, "default-processor")
    return LambdaDefinition(
      function_name=globals.processor_lambda_function_name(iot_device),
      role_name=globals.processor_iam_role_name(iot_device),
      code_path=code_path,
      graph_id=plan_graph_ids.processor_lambda(iot_device),
      environment={"PERSISTER_LAMBDA_NAME": globals.persister_lambda_function_name()},
    )

  def plan(self, previous_iot_device, desired_iot_device):
    previous_function_name = (
      deployment_state.last_applied_processor_lambda_function_name(previous_iot_device)
      if previous_iot_device else None
    )
    if desired_iot_device is None:
      return [plan_action(
        previous_function_name, "lambda_function", action=ACTION_DESTROY,
        graph_id=plan_graph_ids.processor_lambda(previous_iot_device),
      )]
    return plan_lambda(self._lambda_definition(desired_iot_device), previous_function_name)

  def validate_plan(self, action, iot_device):
    definition = self._lambda_definition(iot_device)
    validate_local_plan(action, definition)
    validate_aws_plan(action, definition)

  def deploy(self, iot_device, function_name=None, role_name=None, zip_code=None):
    definition = self._lambda_definition(iot_device)
    create_lambda(definition, function_name=function_name, role_name=role_name, zip_code=zip_code)
    self.log(f"Created Lambda function: {function_name or definition.function_name}")

  def destroy(self, iot_device, function_name=None):
    function_name = function_name or globals.processor_lambda_function_name(iot_device)

    try:
      globals.aws_lambda_client.delete_function(FunctionName=function_name)
      self.log(f"Deleted Lambda function: {function_name}")
    except ClientError as e:
      if e.response["Error"]["Code"] != "ResourceNotFoundException":
        raise

  def info(self, iot_device):
    function_name = globals.processor_lambda_function_name(iot_device)

    try:
      globals.aws_lambda_client.get_function(FunctionName=function_name)
      self.log(f"✅ Processor {function_name} Lambda Function exists: {util.link_to_lambda_function(function_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        self.log(f"❌ Processor {function_name} Lambda Function missing: {function_name}")
      else:
        raise

  def apply(self, action, iot_device, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(iot_device, function_name=resource)
    elif action["action"] == ACTION_DEPLOY:
      code = validate_local_plan(action, self._lambda_definition(iot_device))
      self.deploy(iot_device, function_name=resource, zip_code=code)
    elif action["action"] == ACTION_UPDATE:
      update_lambda(action, self._lambda_definition(iot_device))
      self.log(f"Updated Lambda function: {resource}")
    else:
      raise ValueError(f"Unsupported iot_l2 action: {action['action']}")
