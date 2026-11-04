from deployers.base import Deployer
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.plan_actions import plan_action
from dependency_graph import plan_graph_ids
import deployment_state
import json
import time
import globals
import util
from botocore.exceptions import ClientError

class GrafanaWorkspaceDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def plan(self):
    previous_workspace_name = deployment_state.last_applied_grafana_workspace_name()
    desired_workspace_name = globals.grafana_workspace_name()
    previous_role_name = deployment_state.last_applied_grafana_iam_role_name()
    desired_role_name = globals.grafana_iam_role_name()
    previous_region = deployment_state.last_applied_aws_region()
    desired_region = globals.aws_grafana_client.meta.region_name

    if (
      previous_workspace_name == desired_workspace_name
      and previous_role_name == desired_role_name
      and previous_region == desired_region
    ):
      self.log(f"Grafana Workspace {desired_workspace_name} is up to date in {desired_region}.")
      return [
        plan_action(
          desired_workspace_name,
          "grafana_workspace",
          graph_id=plan_graph_ids.GRAFANA_WORKSPACE,
          region=desired_region,
        )
      ]

    self.log(
      "Grafana Workspace will be redeployed: "
      f"{previous_workspace_name} ({previous_region}) -> "
      f"{desired_workspace_name} ({desired_region})."
    )
    return [
      plan_action(
        previous_workspace_name,
        "grafana_workspace",
        action="DESTROY",
        graph_id=plan_graph_ids.GRAFANA_WORKSPACE,
        region=previous_region,
      ),
      plan_action(
        desired_workspace_name,
        "grafana_workspace",
        action="DEPLOY",
        graph_id=plan_graph_ids.GRAFANA_WORKSPACE,
        region=desired_region,
      ),
    ]

  def deploy(self, workspace_name=None, role_name=None):
    workspace_name = workspace_name or globals.grafana_workspace_name()
    role_name = role_name or globals.grafana_iam_role_name()

    response = globals.aws_iam_client.get_role(RoleName=role_name)
    role_arn = response["Role"]["Arn"]

    response = globals.aws_grafana_client.create_workspace(
      workspaceName=workspace_name,
      workspaceDescription="",
      grafanaVersion="10.4",
      accountAccessType="CURRENT_ACCOUNT",
      authenticationProviders=["AWS_SSO"],
      permissionType="CUSTOMER_MANAGED",
      workspaceRoleArn=role_arn,
      configuration=json.dumps(
        {
          "plugins": {
            "pluginAdminEnabled": True
          },
          # "unifiedAlerting": {
          #   "enabled": True
          # }
        }
      ),
      tags={
          "Environment": "Dev"
      }
    )
    workspace_id = response["workspace"]["id"]

    self.log(f"Creation of Grafana workspace initiated: {workspace_name}")

    while True:
      response = globals.aws_grafana_client.describe_workspace(workspaceId=workspace_id)
      if response["workspace"]["status"] == "ACTIVE":
        break
      time.sleep(2)

    self.log(f"Created Grafana workspace: {workspace_name}")
    self.log(f"Grafana login: https://{response["workspace"]["endpoint"]}")

  def destroy(self, workspace_name=None):
    workspace_name = workspace_name or globals.grafana_workspace_name()

    try:
      workspace_id = util.get_grafana_workspace_id_by_name(workspace_name)
      globals.aws_grafana_client.delete_workspace(workspaceId=workspace_id)
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        return
      else:
        raise

    self.log(f"Deletion of Grafana workspace initiated: {workspace_name}")

    while True:
      try:
        globals.aws_grafana_client.describe_workspace(workspaceId=workspace_id)
        time.sleep(2)
      except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
          break
        else:
          raise

    self.log(f"Deleted Grafana workspace: {workspace_name}")

  def info(self):
    workspace_name = globals.grafana_workspace_name()

    try:
      workspace_id = util.get_grafana_workspace_id_by_name(workspace_name)
      response = globals.aws_grafana_client.describe_workspace(workspaceId=workspace_id)
      self.log(f"✅ Grafana Workspace exists: {util.link_to_grafana_workspace(workspace_id)}")
      self.log(f"Grafana login: https://{response["workspace"]["endpoint"]}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        self.log(f"❌ Grafana Workspace missing: {workspace_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported core_l5 action: {action['action']}")
