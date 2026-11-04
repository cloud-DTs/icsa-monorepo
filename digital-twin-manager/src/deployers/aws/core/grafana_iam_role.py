from deployers.base import Deployer
from deployers.aws.core.trust_policy import service_trust_policy
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.plan_actions import plan_action
from deployers.aws.core import aws_arns
from dependency_graph import plan_graph_ids
import deployment_state
import json
import time
import globals
import util
from botocore.exceptions import ClientError

class GrafanaIamRoleDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def plan(self):
    previous_role_name = deployment_state.last_applied_grafana_iam_role_name()
    desired_role_name = globals.grafana_iam_role_name()

    if previous_role_name == desired_role_name:
      self.log(f"Grafana IAM Role {desired_role_name} is up to date.")
      return [
        plan_action(
          desired_role_name,
          "iam",
          graph_id=plan_graph_ids.GRAFANA_IAM,
        )
      ]

    self.log(f"Grafana IAM Role name changed from {previous_role_name} to {desired_role_name}.")
    return [
      plan_action(
        previous_role_name,
        "iam",
        action="DESTROY",
        graph_id=plan_graph_ids.GRAFANA_IAM,
      ),
      plan_action(
        desired_role_name,
        "iam",
        action="DEPLOY",
        graph_id=plan_graph_ids.GRAFANA_IAM,
      ),
    ]

  def deploy(self, role_name=None):
    role_name = role_name or globals.grafana_iam_role_name()

    response = globals.aws_iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(
          service_trust_policy("grafana.amazonaws.com")
        )
    )
    role_arn = response["Role"]["Arn"]

    self.log(f"Created IAM role: {role_name}")

    self.log(f"Waiting for propagation...")
    time.sleep(20)

    trust_policy = globals.aws_iam_client.get_role(RoleName=role_name)['Role']['AssumeRolePolicyDocument']

    if isinstance(trust_policy['Statement'], dict):
      trust_policy['Statement'] = [trust_policy['Statement']]

    new_statement = {
        "Effect": "Allow",
        "Principal": {
            "AWS": role_arn
        },
        "Action": "sts:AssumeRole"
    }

    trust_policy['Statement'].append(new_statement)

    globals.aws_iam_client.update_assume_role_policy(
        RoleName=role_name,
        PolicyDocument=json.dumps(trust_policy)
    )

    self.log(f"Updated IAM role trust policy: {role_name}")

    policy_name = "GrafanaExecutionPolicy"

    bucket_name = globals.twinmaker_s3_bucket_name()
    workspace_name = globals.twinmaker_workspace_name()

    # Grants match AWS's documented "no video permissions" dashboard policy for
    # the grafana-iot-twinmaker-app plugin:
    # https://docs.aws.amazon.com/iot-twinmaker/latest/guide/dashboard-IAM-role.html
    # iottwinmaker:ListWorkspaces on Resource:"*" is AWS's own requirement (a
    # List-level action that can't be scoped to a single workspace), not a
    # leftover wildcard.
    globals.aws_iam_client.put_role_policy(
      RoleName=role_name,
      PolicyName=policy_name,
      PolicyDocument=json.dumps(
        {
          "Version": "2012-10-17",
          "Statement": [
            {
              "Effect": "Allow",
              "Action": "s3:GetObject",
              "Resource": aws_arns.s3_bucket_objects_arn(bucket_name)
            },
            {
              "Effect": "Allow",
              "Action": [
                "iottwinmaker:Get*",
                "iottwinmaker:List*"
              ],
              "Resource": [
                aws_arns.twinmaker_workspace_arn(workspace_name),
                aws_arns.twinmaker_workspace_children_arn(workspace_name)
              ]
            },
            {
              "Effect": "Allow",
              "Action": "iottwinmaker:ListWorkspaces",
              "Resource": "*"
            }
          ]
        }
      )
    )
    self.log(f"Attached inline IAM policy: {policy_name}")

    self.log(f"Waiting for propagation...")
    time.sleep(20)

  def destroy(self, role_name=None):
    role_name = role_name or globals.grafana_iam_role_name()

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
    role_name = globals.grafana_iam_role_name()

    try:
      globals.aws_iam_client.get_role(RoleName=role_name)
      self.log(f"✅ Grafana IAM Role exists: {util.link_to_iam_role(role_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "NoSuchEntity":
        self.log(f"❌ Grafana IAM Role missing: {role_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported core_l5 action: {action['action']}")
