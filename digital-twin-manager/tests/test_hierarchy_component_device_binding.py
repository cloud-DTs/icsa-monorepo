from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import install_aws_stubs
from tests.test_hot_reader_runtime import DynamoKey, RuntimeDynamoTable

install_aws_stubs()

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.hierarchy.all import AllDeployer as HierarchyAllDeployer
from deployers.aws.hierarchy.twinmaker_hierarchy import TwinmakerHierarchyDeployer
from deployers.aws.iot.l4 import L4Deployer as ComponentTypesDeployer
from validation import config_providers, validate_all_configs
from dependency_graph.dependency_analyzer import analyze_plan_dependencies
from dependency_graph.loader import load_template_graph
from dependency_graph.runtime_graph_builder import build_runtime_graph


def device(device_id="sensor-a", component_type_id=None):
  result = {"id": device_id, "properties": [{"name": "temperature", "dataType": "DOUBLE"}]}
  if component_type_id is not None:
    result["componentTypeId"] = component_type_id
  return result


def hierarchy(component):
  return [{"id": "root-1", "name": "Root", "type": "entity", "children": [component]}]


def component(component_type_id="dt-sensor-a", **extra):
  return {"type": "component", "name": "temperatureSensor", "componentTypeId": component_type_id, **extra}


class BindingTwinmakerClient:
  """AWS boundary with schemas, native property values and entity identity."""

  def __init__(self):
    self.meta = types.SimpleNamespace(region_name="eu-west-1")
    self.component_types = {}
    self.entities = {}
    self.mutations = []
    self.reads = []
    self.identity_counter = 0

  def _error(self, code, operation):
    raise ClientError({"Error": {"Code": code}}, operation)

  def create_component_type(self, workspaceId, componentTypeId, **request):
    key = (workspaceId, componentTypeId)
    if key in self.component_types:
      self._error("ConflictException", "CreateComponentType")
    self.component_types[key] = {
      "workspaceId": workspaceId, "componentTypeId": componentTypeId,
      "status": {"state": "ACTIVE"}, **copy.deepcopy(request),
    }
    self.mutations.append(("create_component_type", key))
    return {"componentTypeId": componentTypeId}

  def get_component_type(self, workspaceId, componentTypeId):
    key = (workspaceId, componentTypeId)
    self.reads.append(("get_component_type", key))
    if key not in self.component_types:
      self._error("ResourceNotFoundException", "GetComponentType")
    return copy.deepcopy(self.component_types[key])

  def create_entity(self, workspaceId, entityId, entityName, **request):
    key = (workspaceId, entityId)
    if key in self.entities:
      self._error("ConflictException", "CreateEntity")
    self.identity_counter += 1
    self.entities[key] = {
      "workspaceId": workspaceId, "entityId": entityId, "entityName": entityName,
      "arn": f"arn:aws:iottwinmaker:eu-west-1:123456789012:workspace/{workspaceId}/entity/{entityId}",
      "creationDateTime": self.identity_counter, "status": {"state": "ACTIVE"},
      "components": {}, **copy.deepcopy(request),
    }
    self.mutations.append(("create_entity", key))
    return {"entityId": entityId}

  def get_entity(self, workspaceId, entityId):
    key = (workspaceId, entityId)
    self.reads.append(("get_entity", key))
    if key not in self.entities:
      self._error("ResourceNotFoundException", "GetEntity")
    return copy.deepcopy(self.entities[key])

  def update_entity(self, workspaceId, entityId, componentUpdates, **request):
    key = (workspaceId, entityId)
    if key not in self.entities:
      self._error("ResourceNotFoundException", "UpdateEntity")
    entity = self.entities[key]
    for name, update in componentUpdates.items():
      update_type = update.get("updateType", "UPDATE")
      if update_type == "DELETE":
        entity["components"].pop(name, None)
        continue
      if update_type == "CREATE":
        if name in entity["components"]:
          self._error("ConflictException", "UpdateEntity")
        type_id = update["componentTypeId"]
        schema = self.component_types.get((workspaceId, type_id))
        if schema is None:
          self._error("ResourceNotFoundException", "UpdateEntity")
        entity["components"][name] = {
          "componentName": name, "componentTypeId": type_id,
          "properties": {
            property_name: {"definition": copy.deepcopy(definition)}
            for property_name, definition in schema.get("propertyDefinitions", {}).items()
          },
          "status": {"state": "ACTIVE"},
        }
      elif name not in entity["components"]:
        self._error("ResourceNotFoundException", "UpdateEntity")
      target = entity["components"][name]
      schema = self.component_types[(workspaceId, target["componentTypeId"])]
      for property_name, property_update in update.get("propertyUpdates", {}).items():
        if property_name not in schema.get("propertyDefinitions", {}):
          self._error("ValidationException", "UpdateEntity")
        if property_update.get("updateType") == "DELETE":
          target["properties"].pop(property_name, None)
        else:
          target["properties"].setdefault(property_name, {})["value"] = copy.deepcopy(property_update["value"])
    self.mutations.append(("update_entity", key, copy.deepcopy(componentUpdates)))
    return {"entityId": entityId}

  def delete_entity(self, workspaceId, entityId, **request):
    key = (workspaceId, entityId)
    if key not in self.entities:
      self._error("ResourceNotFoundException", "DeleteEntity")
    del self.entities[key]
    self.mutations.append(("delete_entity", key))


class BindingLambdaClient:
  def get_function(self, FunctionName):
    return {"Configuration": {"FunctionArn": f"arn:aws:lambda:eu-west-1:123456789012:function:{FunctionName}"}}


class HierarchyComponentDeviceBindingTests(unittest.TestCase):
  def setUp(self):
    self.twinmaker = BindingTwinmakerClient()
    self.table = RuntimeDynamoTable()
    self.deployer = TwinmakerHierarchyDeployer()
    for target, name, value in (
      (globals, "config", {"digital_twin_name": "dt"}),
      (globals, "config_iot_devices", [device()]),
      (globals, "config_hierarchy", hierarchy(component())),
      (globals, "aws_twinmaker_client", self.twinmaker),
      (globals, "aws_lambda_client", BindingLambdaClient()),
      (deployment_state, "last_applied_config", {"digital_twin_name": "dt"}),
      (deployment_state, "last_applied_config_iot_devices", [device()]),
      (deployment_state, "last_applied_config_hierarchy", []),
    ):
      patcher = patch.object(target, name, value, create=True)
      patcher.start()
      self.addCleanup(patcher.stop)
    self.workspace = globals.twinmaker_workspace_name()
    self.reader = self.load_reader()
    self.reader_event = {
      "workspaceId": self.workspace, "entityId": "root-1",
      "componentName": "temperatureSensor", "selectedProperties": ["temperature"],
      "properties": {"temperature": {"definition": {"dataType": {"type": "DOUBLE"}}}},
    }

  def load_reader(self):
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *args, **kwargs: self.twinmaker
    boto3.resource = lambda *args, **kwargs: types.SimpleNamespace(Table=lambda name: self.table)
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Key = DynamoKey
    modules = {
      "boto3": boto3, "boto3.dynamodb": types.ModuleType("boto3.dynamodb"),
      "boto3.dynamodb.conditions": conditions,
    }
    path = REPO_ROOT / "lambda_functions" / "core" / "hot-reader" / "lambda_function.py"
    spec = importlib.util.spec_from_file_location("hot_reader_binding_under_test", path)
    reader = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict(os.environ, {"DIGITAL_TWIN_NAME": "dt", "DYNAMODB_TABLE_NAME": "dt-hot"}):
      spec.loader.exec_module(reader)
    return reader

  def deploy_types(self):
    ComponentTypesDeployer().deploy()
    self.twinmaker.mutations.clear()
    self.twinmaker.reads.clear()

  def assert_reads_sensor_a(self):
    result = self.reader.lambda_handler(self.reader_event, None)
    self.assertEqual(21.25, result["propertyValues"]["temperature"]["propertyValue"]["value"]["doubleValue"])

  def stored_component(self, entity_id="root-1", component_name="temperatureSensor"):
    return self.twinmaker.entities[(self.workspace, entity_id)]["components"][component_name]

  def seed_existing_component(self, value=None, *, entity_id="root-1"):
    """Historical AWS state: a component created before native ID binding."""
    self.twinmaker.create_entity(workspaceId=self.workspace, entityId="root-1", entityName="Root")
    if entity_id != "root-1":
      self.twinmaker.create_entity(
        workspaceId=self.workspace, entityId=entity_id, entityName="Child", parentEntityId="root-1",
      )
    configured_component = globals.config_hierarchy[0]["children"][0]
    if configured_component["type"] == "entity":
      configured_component = configured_component["children"][0]
    update = {"updateType": "CREATE", "componentTypeId": configured_component["componentTypeId"]}
    if value is not None:
      update["propertyUpdates"] = {"iotDeviceId": {"updateType": "CREATE", "value": value}}
    self.twinmaker.update_entity(
      workspaceId=self.workspace, entityId=entity_id,
      componentUpdates={configured_component["name"]: update},
    )
    self.twinmaker.create_component_type(
      workspaceId=self.workspace, componentTypeId="external-control",
      propertyDefinitions={"label": {"dataType": {"type": "STRING"}}},
    )
    self.twinmaker.update_entity(
      workspaceId=self.workspace, entityId="root-1",
      componentUpdates={"notes": {
        "updateType": "CREATE", "componentTypeId": "external-control",
        "propertyUpdates": {"label": {"updateType": "CREATE", "value": {"stringValue": "Keep these notes"}}},
      }},
    )
    self.twinmaker.create_entity(
      workspaceId=self.workspace, entityId="unrelated-child", entityName="Keep this child", parentEntityId="root-1",
    )
    deployment_state.last_applied_config_hierarchy = copy.deepcopy(globals.config_hierarchy)
    deployment_state.last_applied_config_iot_devices = copy.deepcopy(globals.config_iot_devices)
    self.twinmaker.mutations.clear()
    self.twinmaker.reads.clear()
    return copy.deepcopy(self.twinmaker.entities)

  def repair_plan(self):
    plan = HierarchyAllDeployer().plan()
    actions = plan["layers"][0]["actions"]
    self.assertEqual(["UPDATE"], [action["action"] for action in actions])
    self.assertEqual([], self.twinmaker.mutations, "Planning must not change AWS.")
    return plan

  def assert_repair_preserves_hierarchy(self, before, *, entity_id="root-1"):
    plan = self.repair_plan()
    with patch("deployment_state.mark_plan_action_processed") as journal:
      AllDeployer().apply([plan])
    self.assertEqual(1, journal.call_count)
    self.assertEqual(("hierarchy", "hierarchy"), journal.call_args.args[:2])
    expected = copy.deepcopy(before)
    expected[(self.workspace, entity_id)]["components"]["temperatureSensor"]["properties"]["iotDeviceId"]["value"] = {"stringValue": "sensor-a"}
    self.assertEqual(expected, self.twinmaker.entities)
    self.assertTrue(self.twinmaker.mutations)
    self.assertTrue(all(mutation[0] == "update_entity" for mutation in self.twinmaker.mutations))
    self.reader_event["entityId"] = entity_id
    self.assert_reads_sensor_a()
    self.assertEqual(["NO_CHANGE"], [action["action"] for action in self.deployer.plan()])

  def assert_plan_rejected_before_groups(self, plan):
    with patch.object(AllDeployer, "_apply_group") as apply_group:
      with self.assertRaises((ValueError, RuntimeError)):
        AllDeployer().apply([plan])
      apply_group.assert_not_called()
    self.assertEqual([], self.twinmaker.mutations)

  def test_component_type_only_for_single_device_stores_native_id_and_reader_reads(self):
    self.deploy_types()

    self.deployer.deploy()

    self.assert_reads_sensor_a()
    self.assertEqual("sensor-a", self.stored_component()["properties"]["iotDeviceId"]["value"]["stringValue"])

  def test_unique_type_id_uses_configured_device_even_when_names_differ(self):
    globals.config_iot_devices = [device("sensor-a", "industrial-temperature")]
    globals.config_hierarchy = hierarchy(component("dt-industrial-temperature"))
    original_config = copy.deepcopy(globals.config_hierarchy)
    self.deploy_types()

    self.deployer.deploy()

    self.assert_reads_sensor_a()
    self.assertEqual("sensor-a", self.stored_component()["properties"]["iotDeviceId"]["value"]["stringValue"])
    self.assertEqual(original_config, globals.config_hierarchy)

  def test_unique_type_id_from_tree_device_config_is_bound(self):
    globals.config_iot_devices = [{
      "id": "devices", "type": "entity", "children": [{
        "type": "component", "name": "sourceSensor", "iotDeviceId": "sensor-a",
        "componentTypeId": "industrial-temperature", "properties": [{"name": "temperature", "dataType": "DOUBLE"}],
      }],
    }]
    globals.config_hierarchy = hierarchy(component("dt-industrial-temperature"))
    self.deploy_types()

    self.deployer.deploy()

    self.assert_reads_sensor_a()
    self.assertEqual("sensor-a", self.stored_component()["properties"]["iotDeviceId"]["value"]["stringValue"])

  def test_new_unique_binding_can_be_planned_before_managed_type_is_created(self):
    actions = json.loads(json.dumps(self.deployer.plan()))
    self.assertEqual(["DEPLOY"], [action["action"] for action in actions])
    self.assertEqual([], self.twinmaker.mutations)
    self.assertEqual({}, self.twinmaker.component_types)
    HierarchyAllDeployer().validate_plan({"layers": [{"actions": actions}]})
    self.assertEqual([], self.twinmaker.reads)
    self.deploy_types()

    self.deployer.apply(actions[0], actions[0]["resource"])

    self.assert_reads_sensor_a()

  def test_plan_rejects_ambiguous_shared_type_without_device_before_aws_writes(self):
    globals.config_iot_devices = [device("sensor-a", "shared-temperature"), device("sensor-b", "shared-temperature")]
    globals.config_hierarchy = hierarchy(component("dt-shared-temperature"))
    self.deploy_types()

    with self.assertRaisesRegex(ValueError, "iotDeviceId"):
      self.deployer.plan()

    self.assertEqual([], self.twinmaker.mutations)
    self.assertEqual({}, self.twinmaker.entities)

  def test_deploy_rejects_ambiguous_type_in_later_root_before_any_entity_is_created(self):
    globals.config_iot_devices = [device("sensor-a", "shared-temperature"), device("sensor-b", "shared-temperature")]
    globals.config_hierarchy = hierarchy(component("shared-temperature", iotDeviceId="sensor-a"))
    globals.config_hierarchy.append({
      "id": "ambiguous-root", "type": "entity", "children": [{
        "id": "nested", "type": "entity", "children": [component("dt-shared-temperature")],
      }],
    })
    self.deploy_types()

    with self.assertRaisesRegex(ValueError, "iotDeviceId"):
      self.deployer.deploy()

    self.assertEqual([], self.twinmaker.mutations)
    self.assertEqual({}, self.twinmaker.entities)

  def test_explicit_device_id_on_shared_type_stores_and_reads_selected_device(self):
    globals.config_iot_devices = [device("sensor-a", "shared-temperature"), device("sensor-b", "shared-temperature")]
    globals.config_hierarchy = hierarchy(component("shared-temperature", iotDeviceId="sensor-a"))
    self.deploy_types()

    self.deployer.deploy()

    self.assertEqual("dt-shared-temperature", self.stored_component()["componentTypeId"])
    self.assertEqual("sensor-a", self.stored_component()["properties"]["iotDeviceId"]["value"]["stringValue"])
    self.assert_reads_sensor_a()

  def test_external_type_without_managed_config_match_is_allowed_without_inference(self):
    globals.config_hierarchy = hierarchy(component("dt-external-temperature"))
    self.twinmaker.create_component_type(
      workspaceId=self.workspace, componentTypeId="dt-external-temperature",
      propertyDefinitions={"label": {"dataType": {"type": "STRING"}}},
    )
    self.twinmaker.mutations.clear()
    self.twinmaker.reads.clear()

    actions = self.deployer.plan()

    self.assertEqual(["DEPLOY"], [action["action"] for action in actions])
    self.assertEqual([], self.twinmaker.reads)
    self.assertEqual([], self.twinmaker.mutations)
    self.deployer.apply(actions[0], actions[0]["resource"])
    self.assertEqual("dt-external-temperature", self.stored_component()["componentTypeId"])
    self.assertNotIn("iotDeviceId", self.stored_component()["properties"])
    deployment_state.last_applied_config_hierarchy = copy.deepcopy(globals.config_hierarchy)
    self.twinmaker.reads.clear()

    self.assertEqual(["NO_CHANGE"], [action["action"] for action in self.deployer.plan()])
    self.assertEqual([], self.twinmaker.reads)

  def test_old_managed_aws_schema_without_native_id_remains_readable(self):
    self.twinmaker.create_component_type(
      workspaceId=self.workspace, componentTypeId="dt-sensor-a",
      propertyDefinitions={"temperature": {"dataType": {"type": "DOUBLE"}, "isStoredExternally": True, "isTimeSeries": True}},
    )
    self.twinmaker.mutations.clear()

    self.deployer.deploy()

    self.assertNotIn("iotDeviceId", self.stored_component()["properties"])
    self.assert_reads_sensor_a()
    deployment_state.last_applied_config_hierarchy = copy.deepcopy(globals.config_hierarchy)
    self.assertEqual(["NO_CHANGE"], [action["action"] for action in self.deployer.plan()])

  def test_existing_component_with_missing_native_value_is_repaired_in_place(self):
    self.deploy_types()
    before = self.seed_existing_component()

    self.assert_repair_preserves_hierarchy(before)

  def test_existing_nested_component_with_missing_value_is_repaired_without_replacement(self):
    globals.config_hierarchy = [{
      "id": "root-1", "type": "entity", "children": [{
        "id": "nested-room", "type": "entity", "children": [component()],
      }],
    }]
    self.deploy_types()
    before = self.seed_existing_component(entity_id="nested-room")

    self.assert_repair_preserves_hierarchy(before, entity_id="nested-room")

  def test_existing_empty_or_wrong_native_id_is_repaired(self):
    for value in ({"stringValue": ""}, {"stringValue": "sensor-other"}):
      with self.subTest(value=value):
        self.twinmaker.entities.clear()
        self.twinmaker.component_types.clear()
        self.deploy_types()
        before = self.seed_existing_component(value)

        self.assert_repair_preserves_hierarchy(before)

  def test_device_mapping_changed_after_update_plan_rejects_before_root_groups(self):
    globals.config_iot_devices = [device("sensor-a", "industrial-temperature")]
    globals.config_hierarchy = hierarchy(component("dt-industrial-temperature"))
    self.deploy_types()
    before = self.seed_existing_component()
    plan = self.repair_plan()
    globals.config_iot_devices = [device("sensor-b", "industrial-temperature")]

    self.assert_plan_rejected_before_groups(plan)

    self.assertEqual(before, self.twinmaker.entities)

  def test_native_value_changed_in_aws_after_update_plan_rejects_before_root_groups(self):
    self.deploy_types()
    self.seed_existing_component()
    plan = self.repair_plan()
    self.stored_component()["properties"]["iotDeviceId"]["value"] = {"stringValue": "another-writer"}
    before = copy.deepcopy(self.twinmaker.entities)

    self.assert_plan_rejected_before_groups(plan)

    self.assertEqual(before, self.twinmaker.entities)

  def validate_configuration(self):
    validate_all_configs(
      {**globals.config, "hot_storage_size_in_days": 30, "cold_storage_size_in_days": 30},
      {"aws_access_key_id": "A" * 20, "aws_secret_access_key": "a" * 40, "aws_region": "eu-west-1"},
      [], globals.config_hierarchy, globals.config_iot_devices,
      {key: "aws" for key in config_providers.REQUIRED_KEYS},
    )

  def test_alias_declared_in_another_root_binds_type_only_component(self):
    globals.config_hierarchy = hierarchy(component("dt-industrial-temperature")) + [{
      "type": "entity", "id": "source-root", "children": [
        component("industrial-temperature", iotDeviceId="sensor-a"),
      ],
    }]
    self.validate_configuration()
    self.deploy_types()

    self.deployer.deploy()

    self.assert_reads_sensor_a()
    self.assertEqual("sensor-a", self.stored_component()["properties"]["iotDeviceId"]["value"]["stringValue"])

  def test_config_validation_rejects_ambiguous_managed_type_only_reference(self):
    globals.config_iot_devices = [device("sensor-a"), device("sensor-b")]
    globals.config_hierarchy = hierarchy(component("dt-shared-temperature")) + [{
      "type": "entity", "id": "sources", "children": [
        component("shared-temperature", name="sensorA", iotDeviceId="sensor-a"),
        component("shared-temperature", name="sensorB", iotDeviceId="sensor-b"),
      ],
    }]

    with self.assertRaisesRegex(ValueError, "iotDeviceId"):
      self.validate_configuration()

    self.assertEqual([], self.twinmaker.reads)
    self.assertEqual([], self.twinmaker.mutations)

  def test_repair_update_passes_dependency_analysis(self):
    self.deploy_types()
    self.seed_existing_component()
    plan = self.repair_plan()
    template = load_template_graph(REPO_ROOT / "dependency" / "template.json")
    previous = build_runtime_graph(
      template, deployment_state.last_applied_config,
      deployment_state.last_applied_config_iot_devices, [],
      deployment_state.last_applied_config_hierarchy,
    )
    desired = build_runtime_graph(
      template, globals.config, globals.config_iot_devices, [], globals.config_hierarchy,
    )

    analyze_plan_dependencies(previous, desired, [plan])

    action = plan["layers"][0]["actions"][0]
    self.assertEqual("UPDATE", action["action"])
    self.assertFalse(action["blocked"])
    self.assertEqual([], action["blockers"])

  def test_incomplete_response_omitting_required_component_is_reported(self):
    self.deploy_types()
    self.seed_existing_component()
    get_entity = self.twinmaker.get_entity

    def incomplete_entity(**request):
      response = get_entity(**request)
      response["areAllComponentsReturned"] = False
      response["components"].pop("temperatureSensor")
      return response

    with patch.object(self.twinmaker, "get_entity", side_effect=incomplete_entity):
      with self.assertRaisesRegex(ValueError, "incomplete"):
        self.deployer.plan()

    self.assertEqual([], self.twinmaker.mutations)

  def test_incomplete_property_response_cannot_hide_aws_drift(self):
    self.deploy_types()
    self.seed_existing_component()
    plan = self.repair_plan()
    self.stored_component()["properties"]["iotDeviceId"]["value"] = {"stringValue": "another-writer"}
    get_entity = self.twinmaker.get_entity

    def incomplete_properties(**request):
      response = get_entity(**request)
      target = response["components"]["temperatureSensor"]
      target["areAllPropertiesReturned"] = False
      target["properties"].pop("iotDeviceId")
      return response

    with patch.object(self.twinmaker, "get_entity", side_effect=incomplete_properties):
      self.assert_plan_rejected_before_groups(plan)

  def test_partial_response_with_required_scalar_property_can_be_repaired(self):
    self.deploy_types()
    before = self.seed_existing_component()
    get_entity = self.twinmaker.get_entity

    def partial_response(**request):
      response = get_entity(**request)
      response["areAllComponentsReturned"] = False
      response["components"]["temperatureSensor"]["areAllPropertiesReturned"] = False
      return response

    with patch.object(self.twinmaker, "get_entity", side_effect=partial_response):
      self.assert_repair_preserves_hierarchy(before)

  def test_saved_update_without_binding_metadata_is_rejected_before_groups(self):
    self.deploy_types()
    self.seed_existing_component()
    plan = self.repair_plan()
    del plan["layers"][0]["actions"][0]["component_device_bindings"]

    self.assert_plan_rejected_before_groups(plan)

  def test_failed_aws_binding_update_is_not_recorded_as_processed(self):
    self.deploy_types()
    self.seed_existing_component()
    plan = self.repair_plan()
    update_entity = self.twinmaker.update_entity

    def failed_update(**request):
      response = update_entity(**request)
      self.twinmaker.entities[(self.workspace, "root-1")]["status"]["state"] = "ERROR"
      return response

    with (
      patch.object(self.twinmaker, "update_entity", side_effect=failed_update),
      patch("deployment_state.mark_plan_action_processed") as journal,
    ):
      with self.assertRaisesRegex(ValueError, "failed to update"):
        AllDeployer().apply([plan])

    journal.assert_not_called()

  def test_update_that_never_stores_expected_value_times_out_without_journal(self):
    self.deploy_types()
    self.seed_existing_component()
    plan = self.repair_plan()
    update_entity = self.twinmaker.update_entity

    def update_without_value(**request):
      response = update_entity(**request)
      self.stored_component()["properties"]["iotDeviceId"].pop("value")
      return response

    with (
      patch.object(self.twinmaker, "update_entity", side_effect=update_without_value),
      patch("deployers.aws.hierarchy.twinmaker_hierarchy.UPDATE_TIMEOUT_SECONDS", 0),
      patch("deployment_state.mark_plan_action_processed") as journal,
    ):
      with self.assertRaises(TimeoutError):
        AllDeployer().apply([plan])

    journal.assert_not_called()

  def aliased_deploy_plan(self):
    globals.config_iot_devices = [device("sensor-a"), device("sensor-b")]
    source_root = {
      "id": "type-source", "type": "entity", "children": [
        component("shared-temperature", iotDeviceId="sensor-a"),
      ],
    }
    deployment_state.last_applied_config_iot_devices = copy.deepcopy(globals.config_iot_devices)
    deployment_state.last_applied_config_hierarchy = [copy.deepcopy(source_root)]
    globals.config_hierarchy = hierarchy(component("dt-shared-temperature")) + [source_root]
    self.validate_configuration()
    self.deploy_types()
    self.deployer.deploy(hierarchy=deployment_state.last_applied_config_hierarchy)
    self.twinmaker.mutations.clear()
    self.twinmaker.reads.clear()
    return json.loads(json.dumps(HierarchyAllDeployer().plan()))

  def test_deploy_source_changed_in_another_root_rejects_before_any_group(self):
    plan = self.aliased_deploy_plan()
    before = copy.deepcopy(self.twinmaker.entities)
    globals.config_hierarchy[1]["children"][0]["iotDeviceId"] = "sensor-b"
    self.validate_configuration()

    self.assert_plan_rejected_before_groups(plan)

    self.assertEqual(before, self.twinmaker.entities)

  def test_direct_deploy_apply_rejects_changed_binding_before_entity_creation(self):
    plan = self.aliased_deploy_plan()
    action = next(action for action in plan["layers"][0]["actions"] if action["action"] == "DEPLOY")
    globals.config_hierarchy[1]["children"][0]["iotDeviceId"] = "sensor-b"
    self.validate_configuration()

    with self.assertRaisesRegex(ValueError, "plan"):
      self.deployer.apply(action, action["resource"])

    self.assertEqual([], self.twinmaker.mutations)
    self.assertNotIn((self.workspace, "root-1"), self.twinmaker.entities)

  def test_unchanged_deploy_binding_is_preserved_through_apply(self):
    plan = self.aliased_deploy_plan()
    before = copy.deepcopy(self.twinmaker.entities[(self.workspace, "type-source")])

    with patch("deployment_state.mark_plan_action_processed"):
      AllDeployer().apply([plan])

    self.assert_reads_sensor_a()
    self.assertEqual(before, self.twinmaker.entities[(self.workspace, "type-source")])

  def test_replacement_binding_disappeared_after_plan_rejects_before_destroy(self):
    self.deploy_types()
    before = self.seed_existing_component({"stringValue": "sensor-a"})
    globals.config_hierarchy[0]["name"] = "Renamed root"
    plan = HierarchyAllDeployer().plan()
    self.assertEqual(["DESTROY", "DEPLOY"], [a["action"] for a in plan["layers"][0]["actions"]])
    globals.config_iot_devices = [device("sensor-b")]
    self.validate_configuration()

    self.assert_plan_rejected_before_groups(plan)

    self.assertEqual(before, self.twinmaker.entities)

  def test_saved_deploy_without_binding_metadata_rejects_before_groups(self):
    plan = HierarchyAllDeployer().plan()
    plan["layers"][0]["actions"][0].pop("component_device_bindings", None)

    self.assert_plan_rejected_before_groups(plan)

    self.assertEqual([], self.twinmaker.reads)

  def test_external_type_becoming_managed_after_deploy_plan_is_rejected(self):
    globals.config_hierarchy = hierarchy(component("dt-shared-temperature"))
    plan = HierarchyAllDeployer().plan()
    globals.config_hierarchy.append({
      "id": "type-source", "type": "entity", "children": [
        component("shared-temperature", iotDeviceId="sensor-a"),
      ],
    })
    self.validate_configuration()

    self.assert_plan_rejected_before_groups(plan)

  def test_processed_or_blocked_deploy_does_not_require_pending_metadata(self):
    for flag in ("processed", "blocked"):
      with self.subTest(flag=flag):
        plan = HierarchyAllDeployer().plan()
        action = plan["layers"][0]["actions"][0]
        action.pop("component_device_bindings", None)
        action[flag] = True

        HierarchyAllDeployer().validate_plan(plan)

    self.assertEqual([], self.twinmaker.reads)
    self.assertEqual([], self.twinmaker.mutations)


if __name__ == "__main__":
  unittest.main()
