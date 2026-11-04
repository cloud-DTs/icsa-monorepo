import deployment_state
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE
from deployers.aws.core.plan_actions import plan_action
from deployers.aws.core import aws_arns
from deployers.base import Deployer
from deployers.aws.core.trust_policy import service_trust_policy
from dependency_graph import plan_graph_ids
import json
import time
from urllib.parse import unquote
import globals
import util
from botocore.exceptions import ClientError

class HotReaderIamRoleDeployer(Deployer):
  POLICY_NAME = "HotReaderScopedAccess"

  def log(self, message):
    print(f"Core: {message}")

  def _desired_policy_document(self):
    workspace_arn = aws_arns.twinmaker_workspace_arn(globals.twinmaker_workspace_name())
    return {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "dynamodb:Query",
          "Resource": aws_arns.dynamodb_table_arn(globals.hot_dynamodb_table_name()),
        },
        {
          "Effect": "Allow",
          "Action": ["iottwinmaker:GetEntity", "iottwinmaker:GetComponentType"],
          "Resource": [workspace_arn, f"{workspace_arn}/*"],
        },
      ],
    }

  def _put_policy(self, role_name, document):
    globals.aws_iam_client.put_role_policy(
      RoleName=role_name,
      PolicyName=self.POLICY_NAME,
      PolicyDocument=json.dumps(document),
    )
    self.log(f"Updated inline IAM policy: {self.POLICY_NAME}")

  def plan(self):
    previous_role_name = deployment_state.last_applied_hot_reader_iam_role_name()
    desired_role_name = globals.hot_reader_iam_role_name()

    if previous_role_name == desired_role_name:
      try:
        globals.aws_iam_client.get_role(RoleName=desired_role_name)
      except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
          raise
        return [plan_action(
          desired_role_name, "iam", action=ACTION_DEPLOY,
          graph_id=plan_graph_ids.HOT_READER_IAM,
        )]
      try:
        current_document = globals.aws_iam_client.get_role_policy(
          RoleName=desired_role_name, PolicyName=self.POLICY_NAME,
        )["PolicyDocument"]
      except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
          raise
        current_document = None
      if isinstance(current_document, str):
        current_document = json.loads(unquote(current_document))
      desired_document = self._desired_policy_document()
      needs_update = current_document != desired_document
      self.log(f"Hot Reader IAM Role {desired_role_name}: {'UPDATE' if needs_update else 'NO_CHANGE'}.")
      return [
        plan_action(
          desired_role_name,
          "iam",
          action=ACTION_UPDATE if needs_update else "NO_CHANGE",
          graph_id=plan_graph_ids.HOT_READER_IAM,
          policy_document=desired_document,
        )
      ]

    self.log(f"Hot Reader IAM Role name changed from {previous_role_name} to {desired_role_name}.")
    return [
      plan_action(
        previous_role_name,
        "iam",
        action="DESTROY",
        graph_id=plan_graph_ids.HOT_READER_IAM,
      ),
      plan_action(
        desired_role_name,
        "iam",
        action="DEPLOY",
        graph_id=plan_graph_ids.HOT_READER_IAM,
      ),
    ]

  def deploy(self, role_name=None):
    role_name = role_name or globals.hot_reader_iam_role_name()

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
    role_name = role_name or globals.hot_reader_iam_role_name()

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
    role_name = globals.hot_reader_iam_role_name()

    try:
      globals.aws_iam_client.get_role(RoleName=role_name)
      self.log(f"✅ Hot Reader IAM Role exists: {util.link_to_iam_role(role_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "NoSuchEntity":
        self.log(f"❌ Hot Reader IAM Role missing: {role_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    elif action["action"] == ACTION_UPDATE:
      document = action.get("policy_document")
      if document is None or document != self._desired_policy_document():
        raise ValueError("Hot Reader policy changed after planning. Run 'plan' again.")
      self._put_policy(resource, document)
      time.sleep(20)
    else:
      raise ValueError(f"Unsupported core_l3_hot action: {action['action']}")
