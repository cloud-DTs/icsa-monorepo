from deployers.aws.core.plan_actions import plan_action
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.base import Deployer
from dependency_graph import plan_graph_ids
import globals
import deployment_state
import resource_names
from botocore.exceptions import ClientError
import time
import util
from twinmaker_schema import build_data_type, build_property_definitions

class TwinmakerComponentTypeDeployer(Deployer):
  def log(self, message):
    print(f"IoT: {message}")

  def _property_definitions(self, iot_device):
    return build_property_definitions(iot_device)

  def plan(self, previous_iot_device, desired_iot_device):
    previous_connector_function_name = deployment_state.last_applied_hot_reader_lambda_function_name()
    desired_connector_function_name = globals.hot_reader_lambda_function_name()

    previous_workspace_name = deployment_state.last_applied_twinmaker_workspace_name()
    desired_workspace_name = globals.twinmaker_workspace_name()

    previous_component_type_id = (
      deployment_state.last_applied_twinmaker_component_type_id(previous_iot_device)
      if previous_iot_device else None
    )
    desired_component_type_id = (
      globals.twinmaker_component_type_id(desired_iot_device)
      if desired_iot_device else None
    )
    previous_graph_id = (
      plan_graph_ids.device_component_type(
        resource_names.component_type_logical_id(previous_iot_device)
      )
      if previous_iot_device else None
    )
    desired_graph_id = (
      plan_graph_ids.device_component_type(
        resource_names.component_type_logical_id(desired_iot_device)
      )
      if desired_iot_device else None
    )

    previous_property_definitions = (
      self._property_definitions(previous_iot_device)
      if previous_iot_device else {}
    )
    desired_property_definitions = (
      self._property_definitions(desired_iot_device)
      if desired_iot_device else {}
    )

    if previous_iot_device is None:
      self.log(f"TwinMaker Component Type {desired_component_type_id} is new.")
      return [
        plan_action(
          desired_component_type_id,
          "twinmaker_component_type",
          action="DEPLOY",
          graph_id=desired_graph_id,
        ),
      ]

    if desired_iot_device is None:
      self.log(f"TwinMaker Component Type {previous_component_type_id} was removed from config.")
      return [
        plan_action(
          previous_component_type_id,
          "twinmaker_component_type",
          action="DESTROY",
          graph_id=previous_graph_id,
        ),
      ]

    if (
            previous_connector_function_name == desired_connector_function_name
            and previous_workspace_name == desired_workspace_name
            and previous_component_type_id == desired_component_type_id
            and previous_property_definitions == desired_property_definitions
    ):
      self.log(f"TwinMaker Component Type {desired_component_type_id} is up to date.")
      return [
        plan_action(
          desired_component_type_id,
          "twinmaker_component_type",
          graph_id=desired_graph_id,
        ),
      ]

    if previous_connector_function_name != desired_connector_function_name:
      self.log(
        "TwinMaker Component Type connector Lambda function has changed from "
        f"{previous_connector_function_name} to {desired_connector_function_name}"
      )

    if previous_workspace_name != desired_workspace_name:
      self.log(
        f"TwinMaker workspace has changed from {previous_workspace_name} to {desired_workspace_name}"
      )

    if previous_component_type_id != desired_component_type_id:
      self.log(
        "TwinMaker Component Type id has changed from "
        f"{previous_component_type_id} to {desired_component_type_id}"
      )

    if previous_property_definitions != desired_property_definitions:
      self.log(
        f"TwinMaker Component Type properties have changed for {desired_component_type_id}"
      )

    return [
      plan_action(
        previous_component_type_id,
        "twinmaker_component_type",
        action="DESTROY",
        graph_id=previous_graph_id,
      ),
      plan_action(
        desired_component_type_id,
        "twinmaker_component_type",
        action="DEPLOY",
        graph_id=desired_graph_id,
      ),
    ]


  def deploy(
    self,
    iot_device,
    component_type_id=None,
    workspace_name=None,
    connector_function_name=None,
  ):
    connector_function_name = connector_function_name or globals.hot_reader_lambda_function_name()
    workspace_name = workspace_name or globals.twinmaker_workspace_name()
    component_type_id = component_type_id or globals.twinmaker_component_type_id(iot_device)

    response = globals.aws_lambda_client.get_function(FunctionName=connector_function_name)
    connector_function_arn = response["Configuration"]["FunctionArn"]

    property_definitions = self._property_definitions(iot_device)

    functions = {}

    functions = {
      "dataReader": {
        "implementedBy": {
          "lambda": {"arn": connector_function_arn}
        }
      },
      "dataReaderByEntity": {
        "implementedBy": {
          "lambda": {"arn": connector_function_arn}
        }
      },
      "attributePropertyValueReaderByEntity": {
        "implementedBy": {
          "lambda": {"arn": connector_function_arn},
          "isNative": False
        }
      }
    }

    globals.aws_twinmaker_client.create_component_type(
      workspaceId=workspace_name,
      componentTypeId=component_type_id,
      propertyDefinitions=property_definitions,
      functions=functions
    )

    self.log(f"Creation of IoT Twinmaker Component Type initiated: {component_type_id}")

    while True:
      response = globals.aws_twinmaker_client.get_component_type(workspaceId=workspace_name, componentTypeId=component_type_id)
      if response["status"]["state"] == "ACTIVE":
        break
      time.sleep(2)

    self.log(f"Created IoT Twinmaker Component Type: {component_type_id}")

  def destroy(self, iot_device, component_type_id=None, workspace_name=None):
    workspace_name = workspace_name or globals.twinmaker_workspace_name()
    component_type_id = component_type_id or globals.twinmaker_component_type_id(iot_device)

    try:
      globals.aws_twinmaker_client.get_component_type(workspaceId=workspace_name, componentTypeId=component_type_id)
    except ClientError as e:
      if e.response['Error']['Code'] == 'ResourceNotFoundException':
        return

    try:
      response = globals.aws_twinmaker_client.list_entities(workspaceId=workspace_name)

      for entity in response.get("entitySummaries", []):
        entity_details = globals.aws_twinmaker_client.get_entity(workspaceId=workspace_name, entityId=entity["entityId"])
        components = entity_details.get("components", {})
        component_updates = {}

        for comp_name, comp in components.items():
          if comp.get("componentTypeId") == component_type_id:
            component_updates[comp_name] = {"updateType": "DELETE"}

        if component_updates:
          globals.aws_twinmaker_client.update_entity(workspaceId=workspace_name, entityId=entity["entityId"], componentUpdates=component_updates)
          self.log("Deletion of components initiated.")

          while True:
            entity_details_2 = globals.aws_twinmaker_client.get_entity(workspaceId=workspace_name, entityId=entity["entityId"])
            components_2 = entity_details_2.get("components", {})

            if not set(component_updates.keys()) & set(components_2.keys()):
              self.log(f"Deleted components.")
              break
            else:
              time.sleep(2)

    except ClientError as e:
      if e.response["Error"]["Code"] != "ValidationException":
        raise

    self.log(f"Deleted all IoT Twinmaker Components with component type id: {component_type_id}")

    globals.aws_twinmaker_client.delete_component_type(workspaceId=workspace_name, componentTypeId=component_type_id)

    self.log(f"Deletion of IoT Twinmaker Component Type initiated: {component_type_id}")

    while True:
      try:
        globals.aws_twinmaker_client.get_component_type(workspaceId=workspace_name, componentTypeId=component_type_id)
        time.sleep(2)
      except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
          break
        else:
          raise

    self.log(f"Deleted IoT Twinmaker Component Type: {component_type_id}")

  def info(self, iot_device):
    workspace_name = globals.twinmaker_workspace_name()
    component_type_id = globals.twinmaker_component_type_id(iot_device)

    try:
      globals.aws_twinmaker_client.get_component_type(workspaceId=workspace_name, componentTypeId=component_type_id)
      self.log(f"✅ Twinmaker Component Type {component_type_id} exists: {util.link_to_twinmaker_component_type(workspace_name, component_type_id)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        self.log(f"❌ Twinmaker Component Type {component_type_id} missing: {component_type_id}")
      else:
        raise

  def apply(self, action, iot_device, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(
        iot_device,
        component_type_id=resource,
        workspace_name=deployment_state.last_applied_twinmaker_workspace_name(),
      )
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(
        iot_device,
        component_type_id=resource,
        workspace_name=globals.twinmaker_workspace_name(),
        connector_function_name=globals.hot_reader_lambda_function_name(),
      )
    else:
      raise ValueError(f"Unsupported iot_l4 action: {action['action']}")
