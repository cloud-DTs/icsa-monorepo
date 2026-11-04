"""Plan and apply code and configuration updates for manager-owned Lambda functions."""

from copy import deepcopy
from dataclasses import dataclass, field
import time
import zipfile

from botocore.exceptions import ClientError

import globals
import util
from deployers.aws.apply_actions import ACTION_DEPLOY, ACTION_DESTROY, ACTION_NO_CHANGE, ACTION_UPDATE
from deployers.aws.core import aws_arns
from deployers.aws.core.plan_actions import plan_action


CONFIGURATION_FIELDS = ("Runtime", "Handler", "Role", "Timeout", "MemorySize", "Environment")
ROLE_PROPAGATION_MAX_ATTEMPTS = 10
ROLE_PROPAGATION_MAX_DELAY_SECONDS = 8


@dataclass
class LambdaDefinition:
  function_name: str
  role_name: str
  code_path: str
  graph_id: str
  environment: dict = field(default_factory=dict)
  timeout: int = 3
  extra_files: dict = field(default_factory=dict)
  compression: int = zipfile.ZIP_DEFLATED
  preserve_executable: bool = True

  def configuration(self):
    return {
      "Runtime": "python3.13",
      "Handler": "lambda_function.lambda_handler",
      "Role": aws_arns.iam_role_arn(self.role_name),
      "Timeout": self.timeout,
      "MemorySize": 128,
      "Environment": util.lambda_environment(self.environment),
    }

  def package(self):
    return util.compile_reproducible_lambda_function(
      self.code_path, self.extra_files,
      compression=self.compression,
      preserve_executable=self.preserve_executable,
    )


def function_configuration(function_name):
  try:
    return globals.aws_lambda_client.get_function(FunctionName=function_name)["Configuration"]
  except ClientError as error:
    if error.response["Error"]["Code"] == "ResourceNotFoundException":
      return None
    raise


def managed_configuration(configuration):
  fields = {name: deepcopy(configuration.get(name)) for name in CONFIGURATION_FIELDS}
  fields["Environment"] = {"Variables": deepcopy(configuration.get("Environment", {}).get("Variables", {}))}
  return fields


def aws_snapshot(configuration):
  return {
    **managed_configuration(configuration),
    **{name: configuration.get(name) for name in ("CodeSha256", "RevisionId", "State", "LastUpdateStatus")},
  }


def plan_lambda(definition, previous_function_name, *, resource=None, resource_type="lambda_function"):
  resource = definition.function_name if resource is None else resource
  metadata = {
    "code_sha256": util.lambda_code_sha256(definition.package()),
    "lambda_configuration": definition.configuration(),
    "lambda_function_name": definition.function_name,
  }
  actions = []
  if previous_function_name != definition.function_name:
    if previous_function_name is not None:
      actions.append(plan_action(
        previous_function_name if resource_type == "lambda_function" else resource,
        resource_type, action=ACTION_DESTROY, graph_id=definition.graph_id,
      ))
    configuration = None
  else:
    configuration = function_configuration(definition.function_name)

  if configuration is None:
    action_name = ACTION_DEPLOY
  else:
    if configuration.get("LastUpdateStatus") == "InProgress" or configuration.get("State") == "Pending":
      raise RuntimeError(f"Lambda {definition.function_name} is being updated in AWS. Retry planning after completion.")
    if not configuration.get("RevisionId"):
      raise ValueError(f"AWS did not return RevisionId for Lambda {definition.function_name}. Cannot plan a safe update.")
    metadata["revision_id"] = configuration["RevisionId"]
    metadata["aws_configuration"] = aws_snapshot(configuration)
    needs_update = (
      configuration.get("CodeSha256") != metadata["code_sha256"]
      or managed_configuration(configuration) != metadata["lambda_configuration"]
      or configuration.get("LastUpdateStatus") == "Failed"
    )
    action_name = ACTION_UPDATE if needs_update else ACTION_NO_CHANGE

  actions.append(plan_action(resource, resource_type, action=action_name, graph_id=definition.graph_id, **metadata))
  return actions


def needs_lambda_validation(action):
  return (
    action["action"] != ACTION_DESTROY
    and not action.get("processed", False)
    and not action.get("blocked", False)
  )


def validate_local_plan(action, definition):
  if (
    action.get("lambda_function_name") != definition.function_name
    or (action["resource_type"] == "lambda_function" and action["resource"] != definition.function_name)
    or action.get("graph_id") != definition.graph_id
    or action.get("lambda_configuration") != definition.configuration()
    or not action.get("code_sha256")
    or (action["action"] in (ACTION_UPDATE, ACTION_NO_CHANGE) and (
      not action.get("revision_id") or not action.get("aws_configuration")
    ))
  ):
    raise ValueError(f"Lambda {definition.function_name} plan metadata is missing or configuration changed. Run 'plan' again.")
  code = definition.package()
  if util.lambda_code_sha256(code) != action["code_sha256"]:
    raise ValueError(f"Lambda {definition.function_name} code changed after planning. Run 'plan' again.")
  return code


def validate_aws_plan(action, definition, *, allow_replacement=False):
  configuration = function_configuration(definition.function_name)
  if action["action"] == ACTION_DEPLOY:
    if configuration is not None:
      if not allow_replacement:
        raise ValueError(f"Lambda {definition.function_name} already exists in AWS. No replacement is planned. Run 'plan' again.")
      if aws_snapshot(configuration) != action.get("aws_configuration"):
        raise ValueError(f"Lambda {definition.function_name} changed in AWS after planning. Cannot apply the planned replacement. Run 'plan' again.")
  else:
    if configuration is None:
      raise ValueError(f"Lambda {definition.function_name} no longer exists in AWS. Run 'plan' again.")
    if configuration.get("LastUpdateStatus") == "InProgress" or configuration.get("State") == "Pending":
      raise ValueError(f"Lambda {definition.function_name} has an AWS operation in progress. Wait for completion, then run 'plan' again.")
    if configuration.get("RevisionId") != action.get("revision_id"):
      raise ValueError(f"Lambda {definition.function_name} RevisionId changed in AWS after planning. Run 'plan' again.")
    if aws_snapshot(configuration) != action.get("aws_configuration"):
      raise ValueError(f"Lambda {definition.function_name} AWS data no longer matches the saved plan. Run 'plan' again.")
  return configuration


def _is_role_propagation_error(error):
  details = error.response.get("Error", {})
  return (
    error.operation_name == "GetRole" and details.get("Code") == "NoSuchEntity"
  ) or (
    error.operation_name == "CreateFunction"
    and details.get("Code") == "InvalidParameterValueException"
    and "the role defined for the function cannot be assumed by lambda" in details.get("Message", "").lower()
  )


def create_lambda(definition, *, zip_code=None, function_name=None, role_name=None):
  configuration = definition.configuration()
  role_name = role_name or definition.role_name
  function_name = function_name or definition.function_name
  code = definition.package() if zip_code is None else zip_code
  # IAM GetRole visibility does not guarantee that Lambda can assume the role yet.
  for attempt in range(ROLE_PROPAGATION_MAX_ATTEMPTS):
    try:
      configuration["Role"] = globals.aws_iam_client.get_role(RoleName=role_name)["Role"]["Arn"]
      return globals.aws_lambda_client.create_function(
        FunctionName=function_name, Code={"ZipFile": code},
        Description="", Publish=True, **configuration,
      )
    except ClientError as error:
      if not _is_role_propagation_error(error) or attempt == ROLE_PROPAGATION_MAX_ATTEMPTS - 1:
        raise
      delay = min(2 ** attempt, ROLE_PROPAGATION_MAX_DELAY_SECONDS)
      print(
        f"Lambda: IAM role {role_name} is not ready for {function_name}; "
        f"retrying in {delay}s ({attempt + 2}/{ROLE_PROPAGATION_MAX_ATTEMPTS})."
      )
      time.sleep(delay)


def wait_for_update(function_name):
  globals.aws_lambda_client.get_waiter("function_updated_v2").wait(FunctionName=function_name)
  configuration = function_configuration(function_name)
  if configuration is None or configuration.get("LastUpdateStatus") != "Successful":
    raise RuntimeError(f"Lambda {function_name} update did not complete successfully.")
  return configuration


def update_lambda(action, definition):
  code = validate_local_plan(action, definition)
  actual = validate_aws_plan(action, definition)
  desired = action["lambda_configuration"]
  revision_id = action["revision_id"]
  if managed_configuration(actual) != desired:
    response = globals.aws_lambda_client.update_function_configuration(
      FunctionName=definition.function_name, RevisionId=revision_id, **desired,
    )
    # Use the revision returned by our update, never adopt another writer's revision.
    revision_id = response.get("RevisionId")
    updated = wait_for_update(definition.function_name)
    if (
      managed_configuration(updated) != desired
      or updated.get("CodeSha256") != actual.get("CodeSha256")
      or not revision_id
      or updated.get("RevisionId") != revision_id
    ):
      raise RuntimeError(f"Lambda {definition.function_name} changed during its configuration update. Run 'plan' again.")

  globals.aws_lambda_client.update_function_code(
    FunctionName=definition.function_name, ZipFile=code, RevisionId=revision_id, Publish=True,
  )
  updated = wait_for_update(definition.function_name)
  if updated.get("CodeSha256") != action["code_sha256"] or managed_configuration(updated) != desired:
    raise RuntimeError(f"Lambda {definition.function_name} update did not deploy the planned code and configuration.")
