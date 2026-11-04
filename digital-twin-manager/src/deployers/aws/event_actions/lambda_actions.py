import deployment_state
import resource_names
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE
from deployers.aws.core.json_helpers import content_changed
from deployers.aws.core.plan_actions import plan_action
from deployers.base import Deployer
from deployers.aws.lambda_function import (
  LambdaDefinition, aws_snapshot, create_lambda, function_configuration, plan_lambda,
  update_lambda, validate_aws_plan, validate_local_plan,
)
from deployers.aws.core.trust_policy import service_trust_policy
from dependency_graph import plan_graph_ids
import json
import os
import time
import globals
import util
from botocore.exceptions import ClientError

class LambdaActionsDeployer(Deployer):
  def log(self, message):
    print(f"Event Actions: {message}")


  def _create_iam_role(self, role_name):
    globals.aws_iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(
          service_trust_policy("lambda.amazonaws.com")
        )
    )

    self.log(f"Created IAM role: {role_name}")

    policy_arns = [
      "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    ]

    for policy_arn in policy_arns:
      globals.aws_iam_client.attach_role_policy(
        RoleName=role_name,
        PolicyArn=policy_arn
      )

      self.log(f"Attached IAM policy ARN: {policy_arn}")

  def _destroy_iam_role(self, role_name):
    try:
      response = globals.aws_iam_client.list_attached_role_policies(RoleName=role_name)
      for policy in response["AttachedPolicies"]:
          globals.aws_iam_client.detach_role_policy(RoleName=role_name, PolicyArn=policy["PolicyArn"])

      response = globals.aws_iam_client.list_role_policies(RoleName=role_name)
      for policy_name in response["PolicyNames"]:
          globals.aws_iam_client.delete_role_policy(RoleName=role_name, PolicyName=policy_name)

      response = globals.aws_iam_client.list_instance_profiles_for_role(RoleName=role_name)
      for profile in response["InstanceProfiles"]:
        globals.aws_iam_client.remove_role_from_instance_profile(
          InstanceProfileName=profile["InstanceProfileName"],
          RoleName=role_name
        )

      globals.aws_iam_client.delete_role(RoleName=role_name)
      self.log(f"Deleted IAM role: {role_name}")
    except ClientError as e:
      if e.response["Error"]["Code"] != "NoSuchEntity":
        raise

  def _info_iam_role(self, role_name):
    try:
      globals.aws_iam_client.get_role(RoleName=role_name)
      self.log(f"✅ IAM Role exists: {role_name} {util.link_to_iam_role(role_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "NoSuchEntity":
        self.log(f"❌ IAM Role missing: {role_name}")
      else:
        raise


  def _create_lambda_function(self, function_name, path_to_code_folder=None, local_function_name=None, zip_code=None):
    definition = LambdaDefinition(
      function_name=function_name,
      role_name=function_name,
      code_path=path_to_code_folder or os.path.join(globals.event_action_lfs_path, local_function_name),
      graph_id="",
    )
    create_lambda(definition, zip_code=zip_code)
    self.log(f"Created Lambda function: {function_name}")

  def _destroy_lambda_function(self, function_name):
    try:
      globals.aws_lambda_client.delete_function(FunctionName=function_name)
      self.log(f"Deleted Lambda function: {function_name}")
    except ClientError as e:
      if e.response["Error"]["Code"] != "ResourceNotFoundException":
        raise

  def _info_lambda_function(self, function_name):
    try:
      globals.aws_lambda_client.get_function(FunctionName=function_name)
      self.log(f"✅ Lambda Function exists: {function_name} {util.link_to_lambda_function(function_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        self.log(f"❌ Lambda Function missing: {function_name}")
      else:
        raise

  def _root_event_id(self, event: dict) -> str:
    return resource_names.event_action_id(event)

  def _root_events_by_id(self, actions: list[dict]) -> dict[str, dict]:
    events_by_id = {}

    for event in actions:
        event_id = self._root_event_id(event)

        if event_id in events_by_id:
            raise ValueError(f"Duplicate root event action id: {event_id}")

        events_by_id[event_id] = event

    return events_by_id

  def _ordered_root_ids(self, previous_actions_by_id: dict[str, dict], desired_actions_by_id: dict[str, dict]):

    root_ids = []

    for action_id, action in previous_actions_by_id.items():
      root_ids.append(action_id)

    for action_id, action in desired_actions_by_id.items():
      if action_id not in root_ids:
        root_ids.append(action_id)

    return root_ids

  def _root_event(self, events: list[dict], event_id: str) -> dict:
    event = self._root_events_by_id(events).get(event_id)

    if event is None:
      raise ValueError(f"Event Action not found in config: {event_id}")

    return event

  def _event_action_resource_names(self, event: dict, digital_twin_name: str):
    event_action = event["action"]
    function_name = event_action["functionName"]
    resource_name = resource_names.resource_name_from_digital_twin_name(
      digital_twin_name,
      function_name,
    )
    return resource_name, resource_name

  def _deploy_event_action(self, event: dict, digital_twin_name: str, zip_code=None, reuse_role=False):
    event_action = event["action"]

    if event_action["type"] != "lambda" or event_action.get("external"):
      return

    iam_role_name, lambda_function_name = self._event_action_resource_names(
      event,
      digital_twin_name,
    )
    local_function_name = event_action["functionName"]

    if reuse_role:
      try:
        globals.aws_iam_client.get_role(RoleName=iam_role_name)
      except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
          raise
        self._create_iam_role(iam_role_name)
    else:
      self._create_iam_role(iam_role_name)

    self.log(f"Waiting for propagation...")
    time.sleep(20)

    self._create_lambda_function(
      lambda_function_name,
      event_action.get("pathToCode"),
      local_function_name,
      zip_code=zip_code,
    )

  def _destroy_event_action(self, event: dict, digital_twin_name: str):
    event_action = event["action"]

    if event_action["type"] != "lambda" or event_action.get("external"):
      return

    iam_role_name, lambda_function_name = self._event_action_resource_names(
      event,
      digital_twin_name,
    )

    self._destroy_lambda_function(lambda_function_name)
    self._destroy_iam_role(iam_role_name)

  def _lambda_definition(self, event, digital_twin_name=None):
    event_action = event["action"]
    if event_action["type"] != "lambda" or event_action.get("external"):
      return None
    role_name, function_name = self._event_action_resource_names(
      event, digital_twin_name or resource_names.digital_twin_name(globals.config),
    )
    return LambdaDefinition(
      function_name=function_name,
      role_name=role_name,
      code_path=event_action.get("pathToCode") or os.path.join(globals.event_action_lfs_path, event_action["functionName"]),
      graph_id=plan_graph_ids.event_action(self._root_event_id(event)),
    )

  def validate_plan(self, action, replacement_names=()):
    event = self._root_event(globals.config_events, action["resource"])
    definition = self._lambda_definition(event)
    if definition is None:
      if "code_sha256" in action or action["action"] == ACTION_UPDATE:
        raise ValueError("Event Action configuration changed after planning. Run 'plan' again.")
      return
    validate_local_plan(action, definition)
    validate_aws_plan(action, definition, allow_replacement=definition.function_name in replacement_names)

  def replacement_function_names(self, actions):
    names = set()
    for action in actions:
      if action["action"] != ACTION_DESTROY or action.get("blocked", False):
        continue
      event = self._root_event(deployment_state.last_applied_config_events, action["resource"])
      definition = self._lambda_definition(event, deployment_state.last_applied_digital_twin_name())
      if definition is not None:
        names.add(definition.function_name)
    return names

  def plan(self):
    previous = self._root_events_by_id(deployment_state.last_applied_config_events)
    desired = self._root_events_by_id(globals.config_events)
    actions = []
    for action_id in self._ordered_root_ids(previous, desired):
      previous_event = previous.get(action_id)
      desired_event = desired.get(action_id)
      graph_id = plan_graph_ids.event_action(action_id)
      if desired_event is None:
        actions.append(plan_action(action_id, "event_action", action=ACTION_DESTROY, graph_id=graph_id))
        continue
      definition = self._lambda_definition(desired_event)
      if definition is not None:
        previous_definition = (
          self._lambda_definition(previous_event, deployment_state.last_applied_digital_twin_name())
          if previous_event is not None else None
        )
        actions.extend(plan_lambda(
          definition, previous_definition.function_name if previous_definition else None,
          resource=action_id, resource_type="event_action",
        ))
      elif previous_event is None:
        actions.append(plan_action(action_id, "event_action", action=ACTION_DEPLOY, graph_id=graph_id))
      elif content_changed(previous_event, desired_event):
        actions.extend([
          plan_action(action_id, "event_action", action=ACTION_DESTROY, graph_id=graph_id),
          plan_action(action_id, "event_action", action=ACTION_DEPLOY, graph_id=graph_id),
        ])
      else:
        actions.append(plan_action(action_id, "event_action", graph_id=graph_id))
    # A condition change can change the event ID while retaining the Lambda name.
    replacement_names = self.replacement_function_names(actions)
    for action in actions:
      if action["action"] != ACTION_DEPLOY or action.get("lambda_function_name") not in replacement_names:
        continue
      configuration = function_configuration(action["lambda_function_name"])
      if configuration is not None:
        if configuration.get("LastUpdateStatus") == "InProgress" or configuration.get("State") == "Pending":
          raise RuntimeError("Event Action Lambda is being updated in AWS. Retry planning after completion.")
        action["aws_configuration"] = aws_snapshot(configuration)
        action["revision_id"] = configuration.get("RevisionId")
    return actions

  def deploy(self):
    for event in globals.config_events:
      self._deploy_event_action(event, resource_names.digital_twin_name(globals.config))

  def destroy(self):
    for event in globals.config_events:
      self._destroy_event_action(event, resource_names.digital_twin_name(globals.config))

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      event = self._root_event(deployment_state.last_applied_config_events, resource)
      self._destroy_event_action(event, deployment_state.last_applied_digital_twin_name())
    elif action["action"] in (ACTION_DEPLOY, ACTION_UPDATE):
      event = self._root_event(globals.config_events, resource)
      definition = self._lambda_definition(event)
      if definition is None:
        if action["action"] == ACTION_UPDATE or "code_sha256" in action:
          raise ValueError("Event Action configuration changed after planning. Run 'plan' again.")
        return
      if action["action"] == ACTION_UPDATE:
        update_lambda(action, definition)
        self.log(f"Updated Lambda function: {definition.function_name}")
      else:
        code = validate_local_plan(action, definition)
        previous_event = self._root_events_by_id(deployment_state.last_applied_config_events).get(resource)
        previous_definition = (
          self._lambda_definition(previous_event, deployment_state.last_applied_digital_twin_name())
          if previous_event is not None else None
        )
        reuse_role = previous_definition is not None and previous_definition.function_name == definition.function_name
        self._deploy_event_action(
          event, resource_names.digital_twin_name(globals.config), zip_code=code, reuse_role=reuse_role,
        )
    else:
      raise ValueError(f"Unsupported event_actions action: {action['action']}")

  def info(self):
    for event in globals.config_events:
      a = event["action"]
      event_action_iam_role_name = globals.event_action_iam_role_name(a)
      event_action_lambda_function_name = globals.event_action_lambda_function_name(a)

      if a["type"] == "lambda" and not a.get("external"):
        self._info_iam_role(event_action_iam_role_name)
        self._info_lambda_function(event_action_lambda_function_name)
