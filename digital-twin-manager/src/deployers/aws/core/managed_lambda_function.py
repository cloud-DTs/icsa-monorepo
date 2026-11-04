from botocore.exceptions import ClientError

import globals
import util
from deployers.base import Deployer
from deployers.aws.apply_actions import ACTION_DEPLOY, ACTION_DESTROY, ACTION_UPDATE
from deployers.aws.lambda_function import (
  create_lambda, plan_lambda, update_lambda, validate_aws_plan, validate_local_plan,
)


class ManagedLambdaFunctionDeployer(Deployer):
  """Core deployers supply their names, package inputs and Lambda settings."""

  def log(self, message):
    print(f"Core: {message}")

  def _code_package(self):
    return self._lambda_definition().package()

  def plan(self):
    actions = plan_lambda(self._lambda_definition(), self._previous_function_name())
    for action in actions:
      self.log(f"Lambda function {action['resource']}: {action['action']}.")
    return actions

  def validate_code_plan(self, action):
    return validate_local_plan(action, self._lambda_definition())

  def validate_aws_code_plan(self, action):
    return validate_aws_plan(action, self._lambda_definition())

  def deploy(self, function_name=None, role_name=None, zip_code=None):
    definition = self._lambda_definition()
    create_lambda(definition, function_name=function_name, role_name=role_name, zip_code=zip_code)
    self.log(f"Created Lambda function: {function_name or definition.function_name}")

  def update(self, action, function_name):
    definition = self._lambda_definition()
    if function_name != definition.function_name:
      raise ValueError("Lambda function name changed after planning. Run 'plan' again.")
    update_lambda(action, definition)
    self.log(f"Updated Lambda function: {function_name}")

  def destroy(self, function_name=None):
    function_name = function_name or self._function_name()
    try:
      globals.aws_lambda_client.delete_function(FunctionName=function_name)
      self.log(f"Deleted Lambda function: {function_name}")
    except ClientError as error:
      if error.response["Error"]["Code"] != "ResourceNotFoundException":
        raise

  def info(self):
    function_name = self._function_name()
    try:
      globals.aws_lambda_client.get_function(FunctionName=function_name)
      self.log(f"✅ Lambda Function exists: {util.link_to_lambda_function(function_name)}")
    except ClientError as error:
      if error.response["Error"]["Code"] != "ResourceNotFoundException":
        raise
      self.log(f"❌ Lambda Function missing: {function_name}")

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource, zip_code=self.validate_code_plan(action))
    elif action["action"] == ACTION_UPDATE:
      self.update(action, resource)
    else:
      raise ValueError(f"Unsupported core Lambda action: {action['action']}")
