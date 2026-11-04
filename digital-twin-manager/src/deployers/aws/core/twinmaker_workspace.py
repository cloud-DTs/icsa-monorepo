from deployers.base import Deployer
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.plan_actions import plan_action
from dependency_graph import plan_graph_ids
import deployment_state
import time
import globals
import util
from botocore.exceptions import ClientError

class TwinmakerWorkspaceDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def plan(self):
    previous_workspace_name = deployment_state.last_applied_twinmaker_workspace_name()
    desired_workspace_name = globals.twinmaker_workspace_name()
    previous_role_name = deployment_state.last_applied_twinmaker_iam_role_name()
    desired_role_name = globals.twinmaker_iam_role_name()
    previous_bucket_name = deployment_state.last_applied_twinmaker_s3_bucket_name()
    desired_bucket_name = globals.twinmaker_s3_bucket_name()
    previous_region = deployment_state.last_applied_aws_region()
    desired_region = globals.aws_twinmaker_client.meta.region_name

    if (
      previous_workspace_name == desired_workspace_name
      and previous_role_name == desired_role_name
      and previous_bucket_name == desired_bucket_name
      and previous_region == desired_region
    ):
      self.log(f"TwinMaker Workspace {desired_workspace_name} is up to date in {desired_region}.")
      return [
        plan_action(
          desired_workspace_name,
          "twinmaker_workspace",
          graph_id=plan_graph_ids.TWINMAKER_WORKSPACE,
          region=desired_region,
        )
      ]

    self.log(
      "TwinMaker Workspace will be redeployed: "
      f"{previous_workspace_name} ({previous_region}) -> "
      f"{desired_workspace_name} ({desired_region})."
    )
    return [
      plan_action(
        previous_workspace_name,
        "twinmaker_workspace",
        action="DESTROY",
        graph_id=plan_graph_ids.TWINMAKER_WORKSPACE,
        region=previous_region,
      ),
      plan_action(
        desired_workspace_name,
        "twinmaker_workspace",
        action="DEPLOY",
        graph_id=plan_graph_ids.TWINMAKER_WORKSPACE,
        region=desired_region,
      ),
    ]

  def deploy(self, workspace_name=None, role_name=None, bucket_name=None):
    workspace_name = workspace_name or globals.twinmaker_workspace_name()
    role_name = role_name or globals.twinmaker_iam_role_name()
    bucket_name = bucket_name or globals.twinmaker_s3_bucket_name()

    account_id = globals.aws_sts_client.get_caller_identity()['Account']

    globals.aws_twinmaker_client.create_workspace(
      workspaceId=workspace_name,
      role=f"arn:aws:iam::{account_id}:role/{role_name}",
      s3Location=f"arn:aws:s3:::{bucket_name}",
      description=""
    )

    self.log(f"Created IoT TwinMaker workspace: {workspace_name}")

  def destroy(self, workspace_name=None):
    workspace_name = workspace_name or globals.twinmaker_workspace_name()

    try:
      response = globals.aws_twinmaker_client.list_entities(workspaceId=workspace_name)
      deleted_an_entity = False
      for entity in response.get("entitySummaries", []):
        try:
          globals.aws_twinmaker_client.delete_entity(workspaceId=workspace_name, entityId=entity["entityId"], isRecursive=True)
          deleted_an_entity = True
          self.log(f"Deleted IoT TwinMaker entity: {entity["entityId"]}")
        except ClientError as e:
          if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

      if deleted_an_entity:
        self.log(f"Waiting for propagation...")
        time.sleep(20)
    except ClientError as e:
      if e.response["Error"]["Code"] != "ValidationException":
        raise

    try:
      response = globals.aws_twinmaker_client.list_scenes(workspaceId=workspace_name)
      for scene in response.get("sceneSummaries", []):
        try:
          globals.aws_twinmaker_client.delete_scene(workspaceId=workspace_name, sceneId=scene["sceneId"])
          self.log(f"Deleted IoT TwinMaker scene: {scene["sceneId"]}")
        except ClientError as e:
          if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    except ClientError as e:
      if e.response["Error"]["Code"] != "ValidationException":
        raise

    try:
      response = globals.aws_twinmaker_client.list_component_types(workspaceId=workspace_name)
      for componentType in response.get("componentTypeSummaries", []):
        if componentType["componentTypeId"].startswith("com.amazon"):
          continue
        try:
          globals.aws_twinmaker_client.delete_component_type(workspaceId=workspace_name, componentTypeId=componentType["componentTypeId"])
          self.log(f"Deleted IoT TwinMaker component type: {componentType["componentTypeId"]}")
        except ClientError as e:
          if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    except ClientError as e:
      if e.response["Error"]["Code"] != "ValidationException":
        raise

    try:
      globals.aws_twinmaker_client.delete_workspace(workspaceId=workspace_name)
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        return
      else:
        raise

    self.log(f"Deletion of IoT TwinMaker workspace initiated: {workspace_name}")

    while True:
      try:
        globals.aws_twinmaker_client.get_workspace(workspaceId=workspace_name)
        time.sleep(2)
      except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
          break
        else:
          raise

    self.log(f"Deleted IoT TwinMaker workspace: {workspace_name}")

  def info(self):
    workspace_name = globals.twinmaker_workspace_name()

    try:
      globals.aws_twinmaker_client.get_workspace(workspaceId=workspace_name)
      self.log(f"✅ Twinmaker Workspace exists: {util.link_to_twinmaker_workspace(workspace_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        self.log(f"❌ Twinmaker Workspace missing: {workspace_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported core_l4 action: {action['action']}")
