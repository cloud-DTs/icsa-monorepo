from __future__ import annotations

import copy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "test_validation"))

from tests.aws_stubs import install_aws_stubs
from tests.test_hierarchy_component_device_binding import BindingLambdaClient, BindingTwinmakerClient
from validation_helpers import valid_config_set

install_aws_stubs()

import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.core.plan_actions import plan_action
from deployers.aws.iot.all import AllDeployer as IotAllDeployer
from deployers.aws.iot.l4 import L4Deployer
from validation import validate_all_configs


def iot_property(name, data_type="DOUBLE", **extra):
  return {"name": name, "dataType": data_type, **extra}


class UnexpectedAwsClient:
  """Protect invalid-configuration tests from reaching unrelated AWS services."""

  def __init__(self):
    self.meta = types.SimpleNamespace(region_name="eu-west-1")
    self.accesses = []

  def __getattr__(self, name):
    self.accesses.append(name)
    raise AssertionError(f"Invalid shared schema reached AWS API {name} before rejection.")


class SharedComponentSchemaValidationTests(unittest.TestCase):
  def setUp(self):
    self.twinmaker = BindingTwinmakerClient()
    self.deployer = L4Deployer()
    for target, name, value in (
      (globals, "config", {"digital_twin_name": "dt", "hot_storage_size_in_days": 30, "cold_storage_size_in_days": 60}),
      (globals, "config_iot_devices", []),
      (globals, "config_hierarchy", []),
      (globals, "config_events", []),
      (globals, "aws_twinmaker_client", self.twinmaker),
      (globals, "aws_lambda_client", BindingLambdaClient()),
      (deployment_state, "last_applied_config", {"digital_twin_name": "dt", "hot_storage_size_in_days": 30, "cold_storage_size_in_days": 60}),
      (deployment_state, "last_applied_config_iot_devices", []),
      (deployment_state, "last_applied_config_hierarchy", []),
    ):
      patcher = patch.object(target, name, value, create=True)
      patcher.start()
      self.addCleanup(patcher.stop)
    self.aws_guard = UnexpectedAwsClient()
    for name in (
      "aws_iam_client", "aws_iot_client", "aws_sts_client", "aws_sf_client", "aws_s3_client",
      "aws_events_client", "aws_dynamodb_client", "aws_grafana_client", "aws_logs_client", "aws_iot_data_client",
    ):
      patcher = patch.object(globals, name, self.aws_guard)
      patcher.start()
      self.addCleanup(patcher.stop)
    self.configure([iot_property("temperature")], [iot_property("voltage")], earlier_valid_group=True)

  def configure(self, properties_a, properties_b, *, earlier_valid_group=False):
    globals.config_iot_devices = [
      {"id": "sensor-a", "properties": copy.deepcopy(properties_a)},
      {"id": "sensor-b", "properties": copy.deepcopy(properties_b)},
    ]
    children = [
      {"type": "component", "name": "sensorA", "iotDeviceId": "sensor-a", "componentTypeId": "shared-sensor"},
      {"type": "component", "name": "sensorB", "iotDeviceId": "sensor-b", "componentTypeId": "shared-sensor"},
    ]
    if earlier_valid_group:
      globals.config_iot_devices.insert(0, {"id": "auxiliary", "properties": [iot_property("humidity")]})
      children.insert(0, {"type": "component", "name": "auxiliarySensor", "iotDeviceId": "auxiliary"})
    globals.config_hierarchy = [{"id": "root-1", "type": "entity", "children": children}]

  def config_set(self):
    configs = valid_config_set()
    configs["config"] = copy.deepcopy(globals.config)
    configs["config_iot_devices"] = copy.deepcopy(globals.config_iot_devices)
    configs["config_hierarchy"] = copy.deepcopy(globals.config_hierarchy)
    configs["config_events"] = []
    return configs

  def validate_configs(self, configs):
    return validate_all_configs(
      configs["config"], configs["config_credentials"], configs["config_events"],
      configs["config_hierarchy"], configs["config_iot_devices"], configs["config_providers"],
    )

  def compatible_layer_plan(self, *, existing=False):
    self.configure([iot_property("temperature")], [iot_property("temperature")], earlier_valid_group=True)
    if existing:
      deployment_state.last_applied_config_iot_devices = copy.deepcopy(globals.config_iot_devices)
      deployment_state.last_applied_config_hierarchy = copy.deepcopy(globals.config_hierarchy)
    layer = self.deployer.plan()
    shared = next(action for action in layer["actions"] if action["resource"] == "dt-shared-sensor")
    self.assertEqual("NO_CHANGE" if existing else "DEPLOY", shared["action"])
    self.assertEqual([], self.twinmaker.mutations)
    return layer

  def change_nonrepresentative_device_schema(self):
    device = next(device for device in globals.config_iot_devices if device["id"] == "sensor-b")
    device["properties"] = [iot_property("voltage")]

  def iot_group_plan(self, layer):
    return {
      "group": "iot", "layers": [
        {"layer": "iot_l1", "actions": []},
        {"layer": "iot_l2", "actions": []},
        layer,
      ],
    }

  def root_plan(self, layer):
    return [
      {"group": "core", "layers": [{
        "layer": "core_l1", "actions": [plan_action("retired-role", "iam", action="DESTROY")],
      }]},
      self.iot_group_plan(layer),
    ]

  def assert_root_apply_rejected_before_groups(self, layer):
    with patch.object(AllDeployer, "_apply_group") as apply_group:
      with self.assertRaisesRegex(ValueError, "shared-sensor"):
        AllDeployer().apply(self.root_plan(layer))
      apply_group.assert_not_called()
    self.assertEqual([], self.twinmaker.mutations)
    self.assertEqual([], self.aws_guard.accesses)

  def test_direct_deploy_rejects_conflicting_shared_schema_before_earlier_valid_group_mutations(self):
    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      self.deployer.deploy()

    self.assertEqual({}, self.twinmaker.component_types)
    self.assertEqual([], self.twinmaker.mutations)

  def test_l4_plan_keeps_rejecting_conflicting_shared_schema_without_aws_writes(self):
    with self.assertRaisesRegex(ValueError, "shared-sensor") as error:
      self.deployer.plan()

    self.assertIn("sensor-a", str(error.exception))
    self.assertIn("sensor-b", str(error.exception))
    self.assertEqual([], self.twinmaker.mutations)

  def test_validate_all_configs_rejects_conflict_assigned_by_hierarchy(self):
    configs = self.config_set()
    self.assertTrue(all("componentTypeId" not in device for device in configs["config_iot_devices"]))

    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      self.validate_configs(configs)

    self.assertEqual([], self.twinmaker.mutations)
    self.assertEqual([], self.aws_guard.accesses)

  def test_validate_all_configs_uses_its_arguments_instead_of_current_globals(self):
    conflicting = self.config_set()
    self.configure([iot_property("temperature")], [iot_property("temperature")])

    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      self.validate_configs(conflicting)

    self.assertEqual([], self.twinmaker.mutations)

  def test_root_plan_rejects_conflict_before_core_or_aws_reads(self):
    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      AllDeployer().plan()

    self.assertEqual([], self.aws_guard.accesses)
    self.assertEqual([], self.twinmaker.mutations)

  def test_root_deploy_rejects_conflict_before_core_or_prerequisite_writes(self):
    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      AllDeployer().deploy()

    self.assertEqual([], self.aws_guard.accesses)
    self.assertEqual([], self.twinmaker.mutations)

  def test_iot_group_plan_rejects_conflict_before_processor_planning(self):
    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      IotAllDeployer().plan()

    self.assertEqual([], self.aws_guard.accesses)
    self.assertEqual([], self.twinmaker.mutations)

  def test_iot_group_deploy_rejects_conflict_before_device_or_processor_writes(self):
    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      IotAllDeployer().deploy()

    self.assertEqual([], self.aws_guard.accesses)
    self.assertEqual([], self.twinmaker.mutations)

  def test_root_apply_rejects_nonrepresentative_schema_change_before_any_group(self):
    layer = self.compatible_layer_plan()
    self.change_nonrepresentative_device_schema()

    self.assert_root_apply_rejected_before_groups(layer)

  def test_root_apply_rejects_schema_change_even_with_no_change_component_type(self):
    layer = self.compatible_layer_plan(existing=True)
    self.change_nonrepresentative_device_schema()

    self.assert_root_apply_rejected_before_groups(layer)

  def test_direct_l4_apply_rejects_changed_schema_before_earlier_group_creation(self):
    layer = self.compatible_layer_plan()
    self.change_nonrepresentative_device_schema()

    with patch("deployment_state.mark_plan_action_processed") as journal:
      with self.assertRaisesRegex(ValueError, "shared-sensor"):
        self.deployer.apply(layer, "DEPLOY")
      journal.assert_not_called()

    self.assertEqual({}, self.twinmaker.component_types)
    self.assertEqual([], self.twinmaker.mutations)

  def test_direct_l4_apply_validates_conflict_even_when_no_actions_are_pending(self):
    layer = self.compatible_layer_plan(existing=True)
    self.change_nonrepresentative_device_schema()

    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      self.deployer.apply(layer, "DEPLOY")

    self.assertEqual([], self.twinmaker.mutations)

  def test_iot_group_apply_rejects_changed_schema_before_any_layer_mutation(self):
    layer = self.compatible_layer_plan()
    self.change_nonrepresentative_device_schema()

    with patch("deployment_state.mark_plan_action_processed") as journal:
      with self.assertRaisesRegex(ValueError, "shared-sensor"):
        IotAllDeployer().apply(self.iot_group_plan(layer), "DEPLOY")
      journal.assert_not_called()

    self.assertEqual({}, self.twinmaker.component_types)
    self.assertEqual([], self.twinmaker.mutations)
    self.assertEqual([], self.aws_guard.accesses)

  def test_iot_preflight_rejects_changed_no_change_type_without_lambda_actions(self):
    layer = self.compatible_layer_plan(existing=True)
    self.change_nonrepresentative_device_schema()

    with self.assertRaisesRegex(ValueError, "shared-sensor"):
      IotAllDeployer().validate_plan(self.iot_group_plan(layer))

    self.assertEqual([], self.twinmaker.mutations)

  def test_equal_property_schemas_ignore_order_and_per_device_init_values(self):
    self.configure(
      [iot_property("temperature", initValue=20), iot_property("status", "STRING", initValue="ready")],
      [iot_property("status", "STRING", initValue="waiting"), iot_property("temperature", initValue=30)],
    )
    original_devices = copy.deepcopy(globals.config_iot_devices)
    self.validate_configs(self.config_set())
    self.assertEqual(["DEPLOY"], [action["action"] for action in self.deployer.plan()["actions"]])

    self.deployer.deploy()

    self.assertEqual(1, len(self.twinmaker.component_types))
    schema = self.twinmaker.component_types[(globals.twinmaker_workspace_name(), "dt-shared-sensor")]["propertyDefinitions"]
    self.assertEqual({"temperature", "status", "iotDeviceId"}, set(schema))
    self.assertEqual({"type": "DOUBLE"}, schema["temperature"]["dataType"])
    self.assertEqual({"type": "STRING"}, schema["status"]["dataType"])
    self.assertNotIn("initValue", schema["temperature"])
    self.assertEqual(original_devices, globals.config_iot_devices)

  def test_same_property_name_with_different_scalar_or_vector_types_is_rejected(self):
    for left, right in (
      ("DOUBLE", "INTEGER"),
      ("VECTOR_DOUBLE", "VECTOR_INTEGER"),
      ("VECTOR_DOUBLE", "VECTOR_STRING"),
      ("DOUBLE", "VECTOR_DOUBLE"),
    ):
      with self.subTest(left=left, right=right):
        self.configure([iot_property("reading", left)], [iot_property("reading", right)])

        with self.assertRaisesRegex(ValueError, "shared-sensor"):
          self.validate_configs(self.config_set())
        with self.assertRaisesRegex(ValueError, "shared-sensor"):
          self.deployer.deploy()

        self.assertEqual([], self.twinmaker.mutations)

  def test_equal_vector_schemas_deploy_one_correct_shared_type(self):
    for vector_type, element_type in (
      ("VECTOR_DOUBLE", "DOUBLE"),
      ("VECTOR_INTEGER", "INTEGER"),
      ("VECTOR_STRING", "STRING"),
    ):
      with self.subTest(vector_type=vector_type):
        self.twinmaker.component_types.clear()
        self.twinmaker.mutations.clear()
        self.configure([iot_property("reading", vector_type)], [iot_property("reading", vector_type)])
        self.validate_configs(self.config_set())
        self.assertEqual(["DEPLOY"], [action["action"] for action in self.deployer.plan()["actions"]])

        self.deployer.deploy()

        self.assertEqual(1, len(self.twinmaker.component_types))
        schema = self.twinmaker.component_types[(globals.twinmaker_workspace_name(), "dt-shared-sensor")]["propertyDefinitions"]
        self.assertEqual({"type": "LIST", "nestedType": {"type": element_type}}, schema["reading"]["dataType"])

  def test_root_plan_and_deploy_keep_configured_group_order_for_compatible_schema(self):
    self.configure([iot_property("temperature")], [iot_property("temperature")])
    calls = []

    class FirstGroup:
      def plan(self):
        calls.append(("plan", "first"))
        return {"group": "first", "layers": []}

      def deploy(self):
        calls.append(("deploy", "first"))

    class SecondGroup:
      def plan(self):
        calls.append(("plan", "second"))
        return {"group": "second", "layers": []}

      def deploy(self):
        calls.append(("deploy", "second"))

    with patch.object(AllDeployer, "GROUP_DEPLOYERS", {"first": FirstGroup, "second": SecondGroup}):
      planned = AllDeployer().plan()
      AllDeployer().deploy()

    self.assertEqual([{"group": "first", "layers": []}, {"group": "second", "layers": []}], planned)
    self.assertEqual([("plan", "first"), ("plan", "second"), ("deploy", "first"), ("deploy", "second")], calls)


if __name__ == "__main__":
  unittest.main()
