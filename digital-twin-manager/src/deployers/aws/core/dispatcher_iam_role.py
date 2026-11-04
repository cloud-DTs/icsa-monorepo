from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.base import Deployer
from deployers.aws.core.trust_policy import service_trust_policy
from deployers.aws.core.json_helpers import normalized_json
from deployers.aws.core.plan_actions import plan_action
from dependency_graph import plan_graph_ids
import json
import time
import globals
import deployment_state
import util
from botocore.exceptions import ClientError

class DispatcherIamRoleDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def _role(self, role_name):
    try:
      response = globals.aws_iam_client.get_role(RoleName=role_name)
      return response["Role"]
    except ClientError as e:
      if e.response["Error"]["Code"] == "NoSuchEntity":
        return None
      raise

  def _role_exists(self, role_name):
    return self._role(role_name) is not None

  def _role_policy_document(self):
    return service_trust_policy("lambda.amazonaws.com")

  def _policy_arns(self):
    return {
      "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
      "arn:aws:iam::aws:policy/service-role/AWSLambdaRole",
    }

  def _attached_policy_arns(self, role_name):
    response = globals.aws_iam_client.list_attached_role_policies(RoleName=role_name)
    return {
      policy["PolicyArn"]
      for policy in response["AttachedPolicies"]
    }

  def _drift_fields(self, role_name):
    role = self._role(role_name)

    if role is None:
      return ["missing"]

    drift_fields = []
    actual_assume_role_policy = role["AssumeRolePolicyDocument"]
    expected_assume_role_policy = self._role_policy_document()

    if (
      normalized_json(actual_assume_role_policy)
      != normalized_json(expected_assume_role_policy)
    ):
      drift_fields.append("AssumeRolePolicyDocument")

    if self._attached_policy_arns(role_name) != self._policy_arns():
      drift_fields.append("AttachedPolicies")

    return drift_fields

  def plan(self):
    previous_role_name = deployment_state.last_applied_dispatcher_iam_role_name()
    desired_role_name = globals.dispatcher_iam_role_name()

    if previous_role_name == desired_role_name:
      self.log(f"Dispatcher IAM role {desired_role_name} is up to date.")
      return [
        plan_action(
          desired_role_name,
          "iam",
          graph_id=plan_graph_ids.DISPATCHER_IAM,
        )
      ]

    self.log(f"Dispatcher IAM role name changed from {previous_role_name} to {desired_role_name}.")

    return [
      plan_action(
        previous_role_name,
        "iam",
        action="DESTROY",
        graph_id=plan_graph_ids.DISPATCHER_IAM,
      ),
      plan_action(
        desired_role_name,
        "iam",
        action="DEPLOY",
        graph_id=plan_graph_ids.DISPATCHER_IAM,
      ),
    ]


  def deploy(self, role_name=None):
    role_name = role_name or globals.dispatcher_iam_role_name()

    globals.aws_iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(
          self._role_policy_document()
        )
    )

    self.log(f"Created IAM role: {role_name}")

    for policy_arn in self._policy_arns():
      globals.aws_iam_client.attach_role_policy(
        RoleName=role_name,
        PolicyArn=policy_arn
      )

      self.log(f"Attached IAM policy ARN: {policy_arn}")

    self.log(f"Waiting for propagation...")

    time.sleep(20)

  def destroy(self, role_name=None):
    role_name = role_name or globals.dispatcher_iam_role_name()

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
    role_name = globals.dispatcher_iam_role_name()

    try:
      globals.aws_iam_client.get_role(RoleName=role_name)
      self.log(f"✅ Dispatcher IAM Role exists: {util.link_to_iam_role(role_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "NoSuchEntity":
        self.log(f"❌ Dispatcher IAM Role missing: {role_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported core_l1 action: {action['action']}")
