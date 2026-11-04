from deployers.base import Deployer
from deployers.aws.core.trust_policy import service_trust_policy
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE, ACTION_NO_CHANGE
from deployers.aws.core.plan_actions import plan_action
from deployers.aws.core import aws_arns
from dependency_graph import plan_graph_ids
import json
import time
from copy import deepcopy
from urllib.parse import unquote
import globals
import deployment_state
import util
from botocore.exceptions import ClientError

class EventCheckerIamRoleDeployer(Deployer):
  POLICY_NAME = "EventCheckerScopedAccess"

  def log(self, message):
    print(f"Core: {message}")

  def _desired_policy_document(self):
    workspace_name = globals.twinmaker_workspace_name()
    workspace_arn = aws_arns.twinmaker_workspace_arn(workspace_name)
    digital_twin_name = globals.config["digital_twin_name"]
    return {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "iottwinmaker:GetWorkspace",
          "Resource": workspace_arn,
        },
        # Property reads also require access to entity and component metadata.
        # https://docs.aws.amazon.com/service-authorization/latest/reference/list_iottwinmaker.html
        {
          "Effect": "Allow",
          "Action": "iottwinmaker:GetComponentType",
          "Resource": [workspace_arn, f"{workspace_arn}/component-type/*"],
        },
        {
          "Effect": "Allow",
          "Action": "iottwinmaker:GetEntity",
          "Resource": [workspace_arn, f"{workspace_arn}/entity/*"],
        },
        {
          "Effect": "Allow",
          "Action": ["iottwinmaker:GetPropertyValueHistory", "iottwinmaker:GetPropertyValue"],
          "Resource": [
            aws_arns.twinmaker_workspace_arn(workspace_name),
            aws_arns.twinmaker_workspace_children_arn(workspace_name),
          ],
        },
        {
          "Effect": "Allow",
          "Action": ["lambda:GetFunction", "lambda:InvokeFunction"],
          "Resource": aws_arns.lambda_function_name_wildcard_arn(f"{digital_twin_name}-"),
        },
        {
          "Effect": "Allow",
          "Action": "states:StartExecution",
          "Resource": aws_arns.state_machine_arn(globals.lambda_chain_step_function_name()),
        },
      ],
    }

  def _current_policy_document(self, role_name):
    try:
      document = globals.aws_iam_client.get_role_policy(
        RoleName=role_name, PolicyName=self.POLICY_NAME,
      )["PolicyDocument"]
    except ClientError as error:
      if error.response["Error"]["Code"] != "NoSuchEntity":
        raise
      return None
    if isinstance(document, str):
      document = json.loads(unquote(document))
    return deepcopy(document)

  def _put_policy(self, role_name, document):
    # PutRolePolicy updates the inline document without replacing the IAM role.
    # https://docs.aws.amazon.com/IAM/latest/APIReference/API_PutRolePolicy.html
    globals.aws_iam_client.put_role_policy(
      RoleName=role_name, PolicyName=self.POLICY_NAME,
      PolicyDocument=json.dumps(document),
    )
    self.log(f"Updated inline IAM policy: {self.POLICY_NAME}")

  def plan(self):
    previous_role_name = deployment_state.last_applied_event_checker_iam_role_name()
    desired_role_name = globals.event_checker_iam_role_name()
    desired_document = self._desired_policy_document()

    if previous_role_name == desired_role_name:
      try:
        globals.aws_iam_client.get_role(RoleName=desired_role_name)
      except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
          raise
        return [plan_action(
          desired_role_name, "iam", action=ACTION_DEPLOY,
          graph_id=plan_graph_ids.EVENT_CHECKER_IAM,
          policy_document=desired_document,
        )]
      current_document = self._current_policy_document(desired_role_name)
      action_name = ACTION_UPDATE if current_document != desired_document else ACTION_NO_CHANGE
      self.log(f"Event-Checker IAM Role {desired_role_name}: {action_name}.")
      return [
        plan_action(
          desired_role_name,
          "iam",
          action=action_name,
          graph_id=plan_graph_ids.EVENT_CHECKER_IAM,
          policy_document=desired_document,
          aws_policy_document=current_document,
        )
      ]

    self.log(f"Event-Checker IAM Role name changed from {previous_role_name} to {desired_role_name}.")
    return [
      plan_action(
        previous_role_name,
        "iam",
        action="DESTROY",
        graph_id=plan_graph_ids.EVENT_CHECKER_IAM,
      ),
      plan_action(
        desired_role_name,
        "iam",
        action="DEPLOY",
        graph_id=plan_graph_ids.EVENT_CHECKER_IAM,
          policy_document=desired_document,
      ),
    ]

  def validate_plan(self, action):
    if action.get("resource") != globals.event_checker_iam_role_name():
      raise ValueError("Event Checker role name changed after planning. Run 'plan' again.")
    if "policy_document" not in action:
      raise ValueError("Event Checker policy metadata is missing. Run 'plan' again.")
    if action["policy_document"] != self._desired_policy_document():
      raise ValueError("Event Checker policy configuration changed after planning. Run 'plan' again.")
    if action["action"] == ACTION_DEPLOY:
      try:
        globals.aws_iam_client.get_role(RoleName=action["resource"])
      except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
          raise
        return
      raise ValueError("Event Checker role already exists in AWS. Run 'plan' again.")
    if action["action"] in (ACTION_UPDATE, ACTION_NO_CHANGE):
      if "aws_policy_document" not in action:
        raise ValueError("Event Checker AWS policy metadata is missing. Run 'plan' again.")
      try:
        globals.aws_iam_client.get_role(RoleName=action["resource"])
      except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
          raise
        raise ValueError("Event Checker role no longer exists in AWS. Run 'plan' again.") from error
      if self._current_policy_document(action["resource"]) != action["aws_policy_document"]:
        raise ValueError("Event Checker policy changed in AWS after planning. Run 'plan' again.")

  def deploy(self, role_name=None):
    role_name = role_name or globals.event_checker_iam_role_name()

    globals.aws_iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(
          service_trust_policy("lambda.amazonaws.com")
        )
    )

    self.log(f"Created IAM role: {role_name}")

    policy_arns = [
      "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    ]

    for policy_arn in policy_arns:
      globals.aws_iam_client.attach_role_policy(
        RoleName=role_name,
        PolicyArn=policy_arn
      )

      self.log(f"Attached IAM policy ARN: {policy_arn}")

    self._put_policy(role_name, self._desired_policy_document())

    self.log(f"Waiting for propagation...")

    time.sleep(20)

  def destroy(self, role_name=None):
    role_name = role_name or globals.event_checker_iam_role_name()

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

  def info(self):
    role_name = globals.event_checker_iam_role_name()

    try:
      globals.aws_iam_client.get_role(RoleName=role_name)
      self.log(f"✅ Event-Checker IAM Role exists: {util.link_to_iam_role(role_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "NoSuchEntity":
        self.log(f"❌ Event-Checker IAM Role missing: {role_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] in (ACTION_DEPLOY, ACTION_UPDATE):
      if resource != action.get("resource"):
        raise ValueError("Event Checker role does not match the planned resource. Run 'plan' again.")
      self.validate_plan(action)
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    elif action["action"] == ACTION_UPDATE:
      self._put_policy(resource, action["policy_document"])
      time.sleep(20)
    else:
      raise ValueError(f"Unsupported core_l2 action: {action['action']}")
