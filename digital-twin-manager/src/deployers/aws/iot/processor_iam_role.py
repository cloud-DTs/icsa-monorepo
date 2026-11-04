import deployment_state
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.plan_actions import plan_action
from deployers.base import Deployer
from deployers.aws.core.trust_policy import service_trust_policy
from dependency_graph import plan_graph_ids
import json
import globals
from botocore.exceptions import ClientError
import util

class ProcessorIamRoleDeployer(Deployer):
  def log(self, message):
    print(f"IoT: {message}")

  def plan(self, previous_iot_device, desired_iot_device):
    previous_role_name = (
      deployment_state.last_applied_processor_iam_role_name(previous_iot_device)
      if previous_iot_device else None
    )
    desired_role_name = (
      globals.processor_iam_role_name(desired_iot_device)
      if desired_iot_device else None
    )
    previous_graph_id = (
      plan_graph_ids.processor_iam(previous_iot_device)
      if previous_iot_device else None
    )
    desired_graph_id = (
      plan_graph_ids.processor_iam(desired_iot_device)
      if desired_iot_device else None
    )

    if previous_iot_device is None:
      self.log(f"IAM role {desired_role_name} is new.")
      return [
        plan_action(
          desired_role_name,
          "iam",
          action="DEPLOY",
          graph_id=desired_graph_id,
        ),
      ]

    if desired_iot_device is None:
      self.log(f"IAM role {previous_role_name} was removed from config.")
      return [
        plan_action(
          previous_role_name,
          "iam",
          action="DESTROY",
          graph_id=previous_graph_id,
        ),
      ]

    if previous_role_name == desired_role_name:
      self.log(f"IAM role {desired_role_name} is up to date.")
      return [
        plan_action(
          desired_role_name,
          "iam",
          graph_id=desired_graph_id,
        ),
      ]

    self.log(f"IAM role name has changed from {previous_role_name} to {desired_role_name}")

    return [
      plan_action(
        previous_role_name,
        "iam",
        action="DESTROY",
        graph_id=previous_graph_id,
      ),
      plan_action(
        desired_role_name,
        "iam",
        action="DEPLOY",
        graph_id=desired_graph_id,
      ),
    ]

  def deploy(self, iot_device, role_name=None):
    role_name = role_name or globals.processor_iam_role_name(iot_device)

    globals.aws_iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(
          service_trust_policy("lambda.amazonaws.com")
        )
    )

    self.log(f"Created IAM role: {role_name}")

    policy_arns = [
      "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
      "arn:aws:iam::aws:policy/service-role/AWSLambdaRole"
    ]

    for policy_arn in policy_arns:
      globals.aws_iam_client.attach_role_policy(
        RoleName=role_name,
        PolicyArn=policy_arn
      )

      self.log(f"Attached IAM policy ARN: {policy_arn}")

  def destroy(self, iot_device, role_name=None):
    role_name = role_name or globals.processor_iam_role_name(iot_device)

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

  def info(self, iot_device):
    role_name = globals.processor_iam_role_name(iot_device)

    try:
      globals.aws_iam_client.get_role(RoleName=role_name)
      self.log(f"✅ Processor {role_name} IAM Role exists: {util.link_to_iam_role(role_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "NoSuchEntity":
        self.log(f"❌ Processor {role_name} IAM Role missing: {role_name}")
      else:
        raise

  def apply(self, action, iot_device, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(iot_device, role_name=resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(iot_device, role_name=resource)
    else:
      raise ValueError(f"Unsupported iot_l2 action: {action['action']}")
