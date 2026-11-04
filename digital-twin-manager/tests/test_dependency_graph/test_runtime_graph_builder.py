from __future__ import annotations
import unittest
from dependency_graph_helpers import TEMPLATE_PATH, template_node

import resource_names
from dependency_graph.dependency_analyzer import analyze_plan_dependencies
from dependency_graph.loader import load_template_graph
from dependency_graph.models import (
  DependencyType,
  RuntimeGraph,
  TemplateDependency,
  TemplateGraph,
  TemplateNode,
)
from dependency_graph.runtime_graph_builder import build_runtime_graph
from deployers.aws.core.plan_actions import plan_action


class RuntimeGraphBuilderTests(unittest.TestCase):
  def test_iot_policy_and_version_are_shared_across_devices(self) -> None:
    template = load_template_graph(TEMPLATE_PATH)
    graph = build_runtime_graph(
      template, config(), [{"id": "sensor-1"}, {"id": "sensor-2"}], [], [],
    )
    nodes = runtime_nodes_by_id(graph)
    for template_id in ("iot:l1:iot_policy:iot_policy", "iot:l1:iot_policy_version:iot_policy_version"):
      policies = [node for node in graph.nodes if node.template_id == template_id]
      self.assertEqual(1, len(policies))
      self.assertEqual("dt-iot-policy", policies[0].physical_name)
      self.assertEqual("IotPolicyDeployer", policies[0].owner_deployer)

    policy_id = "iot:l1:iot_policy:iot_policy:iot-policy"
    for device_id in ("sensor-1", "sensor-2"):
      self.assertIn(policy_id, dependency_ids(nodes[f"iot:l1:iot_thing:iot_thing:{device_id}"]))
      attachment = nodes[f"iot:l1:iot_policy_certificate_attachment:iot_policy_attachment:{device_id}"]
      self.assertIn(policy_id, dependency_ids(attachment))

  def test_twin_with_no_devices_still_has_one_shared_iot_policy(self) -> None:
    graph = build_runtime_graph(load_template_graph(TEMPLATE_PATH), config(), [], [], [])
    policies = [node for node in graph.nodes if node.template_id == "iot:l1:iot_policy:iot_policy"]
    self.assertEqual(1, len(policies))
    self.assertEqual("dt-iot-policy", policies[0].physical_name)

  def test_runtime_graph_builds_shared_core_nodes(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("core:l3_hot:hot_dynamodb_table:dynamodb_table"),
        TemplateNode(
          id="core:l3_hot:hot_dynamodb_backup:dynamodb_backup",
          owner_deployer="HotDynamodbTableDeployer",
          depends_on=(
            TemplateDependency(
              id="core:l3_hot:hot_dynamodb_table:dynamodb_table",
              type=DependencyType.CREATE_AFTER,
            ),
          ),
          lifecycle_artifact=True,
        ),
      ),
    )

    runtime_graph = build_runtime_graph(graph, config(), [], [], [])
    nodes_by_id = runtime_nodes_by_id(runtime_graph)
    table_node = nodes_by_id[
      "core:l3_hot:hot_dynamodb_table:dynamodb_table:hot-iot-data"
    ]
    backup_node = nodes_by_id[
      "core:l3_hot:hot_dynamodb_backup:dynamodb_backup:hot-iot-data-backup"
    ]

    self.assertEqual("hot-iot-data", table_node.logical_name)
    self.assertEqual("dt-hot-iot-data", table_node.physical_name)
    self.assertEqual("TestDeployer", table_node.owner_deployer)
    self.assertFalse(table_node.lifecycle_artifact)
    self.assertTrue(backup_node.lifecycle_artifact)
    self.assertEqual(
      ["core:l3_hot:hot_dynamodb_table:dynamodb_table:hot-iot-data"],
      dependency_ids(backup_node),
    )

  def test_runtime_graph_builds_iot_l1_device_resources(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("iot:l1:iot_thing:iot_thing"),
        template_node(
          "iot:l1:iot_certificate:iot_certificate",
          "iot:l1:iot_thing:iot_thing",
        ),
        template_node(
          "iot:l1:iot_auth_files:local_auth_files",
          "iot:l1:iot_certificate:iot_certificate",
        ),
      ),
    )

    runtime_graph = build_runtime_graph(
      graph,
      config(),
      [{"id": "sensor-1", "properties": []}],
      [],
      [],
    )
    nodes_by_id = runtime_nodes_by_id(runtime_graph)
    thing_node = nodes_by_id["iot:l1:iot_thing:iot_thing:sensor-1"]
    certificate_node = nodes_by_id["iot:l1:iot_certificate:iot_certificate:sensor-1"]
    auth_files_node = nodes_by_id["iot:l1:iot_auth_files:local_auth_files:sensor-1"]

    self.assertEqual("dt-sensor-1", thing_node.physical_name)
    self.assertIsNone(certificate_node.physical_name)
    self.assertEqual("iot_devices_auth/sensor-1", auth_files_node.physical_name)
    self.assertEqual(
      ["iot:l1:iot_thing:iot_thing:sensor-1"],
      dependency_ids(certificate_node),
    )
    self.assertEqual(
      ["iot:l1:iot_certificate:iot_certificate:sensor-1"],
      dependency_ids(auth_files_node),
    )

  def test_runtime_graph_builds_iot_l2_processor_dependencies(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("iot:l2:processor_iam:iam"),
        template_node(
          "iot:l2:processor_lambda:lambda_function",
          "iot:l2:processor_iam:iam",
        ),
      ),
    )

    runtime_graph = build_runtime_graph(
      graph,
      config(),
      [{"id": "sensor-1", "properties": []}],
      [],
      [],
    )
    nodes_by_id = runtime_nodes_by_id(runtime_graph)
    lambda_node = nodes_by_id[
      "iot:l2:processor_lambda:lambda_function:sensor-1-processor"
    ]

    self.assertEqual("sensor-1-processor", lambda_node.logical_name)
    self.assertEqual("dt-sensor-1-processor", lambda_node.physical_name)
    self.assertEqual(
      ["iot:l2:processor_iam:iam:sensor-1-processor"],
      dependency_ids(lambda_node),
    )

  def test_runtime_graph_builds_hierarchy_to_component_type_dependencies(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("core:l4:twinmaker_workspace:twinmaker_workspace"),
        template_node(
          "iot:l4:device_component_type:twinmaker_component_type",
          "core:l4:twinmaker_workspace:twinmaker_workspace",
        ),
        TemplateNode(
          id="hierarchy:hierarchy:twinmaker_hierarchy:twinmaker_hierarchy",
          owner_deployer="TwinmakerHierarchyDeployer",
          depends_on=(
            TemplateDependency(
              id="iot:l4:device_component_type:twinmaker_component_type",
              type=DependencyType.RUNTIME_USES,
            ),
          ),
        ),
        template_node(
          "hierarchy:hierarchy:twinmaker_entity:twinmaker_entity",
          "hierarchy:hierarchy:twinmaker_hierarchy:twinmaker_hierarchy",
        ),
        template_node(
          "hierarchy:hierarchy:twinmaker_component:twinmaker_component",
          "hierarchy:hierarchy:twinmaker_entity:twinmaker_entity",
          "iot:l4:device_component_type:twinmaker_component_type",
        ),
      ),
    )

    runtime_graph = build_runtime_graph(
      graph,
      {"digital_twin_name": "dt"},
      [{"id": "sensor-1", "properties": []}],
      [],
      [
        {
          "id": "root-1",
          "type": "entity",
          "children": [
            {
              "id": "room-1",
              "type": "entity",
              "children": [
                {
                  "type": "component",
                  "name": "temperature",
                  "iotDeviceId": "sensor-1",
                },
              ],
            },
          ],
        },
      ],
    )
    nodes_by_id = {node.id: node for node in runtime_graph.nodes}

    root_node = nodes_by_id[
      "hierarchy:hierarchy:twinmaker_hierarchy:twinmaker_hierarchy:root-1"
    ]
    component_node = nodes_by_id[
      "hierarchy:hierarchy:twinmaker_component:twinmaker_component:room-1.temperature"
    ]

    self.assertIn(
      "iot:l4:device_component_type:twinmaker_component_type:sensor-1",
      [dependency.id for dependency in root_node.depends_on],
    )
    self.assertEqual(
      {
        "hierarchy:hierarchy:twinmaker_entity:twinmaker_entity:room-1",
        "iot:l4:device_component_type:twinmaker_component_type:sensor-1",
      },
      {dependency.id for dependency in component_node.depends_on},
    )

  def test_runtime_graph_builds_init_value_publish_dependencies(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("iot:l2:processor_lambda:lambda_function"),
        template_node("init_values:init_values:init_value:init_value"),
        template_node(
          "init_values:init_values:init_value_mqtt_publish:iot_message",
          "init_values:init_values:init_value:init_value",
          "iot:l2:processor_lambda:lambda_function",
        ),
      ),
    )

    runtime_graph = build_runtime_graph(
      graph,
      {"digital_twin_name": "dt"},
      [
        {
          "id": "sensor-1",
          "properties": [
            {
              "name": "temperature",
              "dataType": "DOUBLE",
              "initValue": 20,
            },
          ],
        },
      ],
      [],
      [],
    )
    nodes_by_id = {node.id: node for node in runtime_graph.nodes}
    publish_node = nodes_by_id[
      "init_values:init_values:init_value_mqtt_publish:iot_message:sensor-1"
    ]

    self.assertEqual(
      {
        "init_values:init_values:init_value:init_value:sensor-1",
        "iot:l2:processor_lambda:lambda_function:sensor-1-processor",
      },
      {dependency.id for dependency in publish_node.depends_on},
    )

  def test_logical_component_type_names_preserve_twin_prefix(self) -> None:
    for logical_name in ("pac-sensor", "dt-pac-sensor", "dt-dt-pac-sensor"):
      with self.subTest(logical_name=logical_name):
        self._assert_hierarchy_component_type_dependency(
          [{"id": "sensor-1", "componentTypeId": logical_name, "properties": []}],
          {"iotDeviceId": "sensor-1", "componentTypeId": logical_name},
          logical_name,
        )

  def test_full_component_type_references_remove_only_workspace_prefix(self) -> None:
    for logical_name in ("pac-sensor", "dt-pac-sensor", "dt-dt-pac-sensor"):
      with self.subTest(logical_name=logical_name):
        self._assert_hierarchy_component_type_dependency(
          [{"id": "sensor-1", "componentTypeId": logical_name, "properties": []}],
          {"componentTypeId": f"dt-{logical_name}"},
          logical_name,
        )

  def test_device_id_only_reference_preserves_twin_prefix(self) -> None:
    self._assert_hierarchy_component_type_dependency(
      [{"id": "dt-pac-sensor", "properties": []}],
      {"iotDeviceId": "dt-pac-sensor"},
      "dt-pac-sensor",
    )

  def test_prefixed_logical_type_does_not_depend_on_other_unprefixed_type(self) -> None:
    self._assert_hierarchy_component_type_dependency(
      [
        {"id": "sensor-1", "componentTypeId": "dt-pac-sensor", "properties": []},
        {"id": "sensor-2", "componentTypeId": "pac-sensor", "properties": []},
      ],
      {"iotDeviceId": "sensor-1", "componentTypeId": "dt-pac-sensor"},
      "dt-pac-sensor",
    )

  def _assert_hierarchy_component_type_dependency(self, devices, component, logical_name):
    graph = build_runtime_graph(
      load_template_graph(TEMPLATE_PATH), config(), devices, [],
      [{
        "id": "root-1", "type": "entity", "children": [{
          "id": "room-1", "type": "entity", "children": [{
            "type": "component", "name": "temperature", **component,
          }],
        }],
      }],
    )
    nodes = runtime_nodes_by_id(graph)
    type_template_id = "iot:l4:device_component_type:twinmaker_component_type"
    expected_type_id = f"{type_template_id}:{logical_name}"
    root_id = "hierarchy:hierarchy:twinmaker_hierarchy:twinmaker_hierarchy:root-1"
    component_id = "hierarchy:hierarchy:twinmaker_component:twinmaker_component:room-1.temperature"

    self.assertEqual(f"dt-{logical_name}", nodes[expected_type_id].physical_name)
    for node_id in (root_id, component_id):
      self.assertEqual(
        {expected_type_id},
        {dependency.id for dependency in nodes[node_id].depends_on if dependency.template_id == type_template_id},
      )

    action = plan_action("root-1", "twinmaker_hierarchy", action="DEPLOY", graph_id=root_id)
    analyze_plan_dependencies(
      RuntimeGraph(version=graph.version, nodes=()), graph,
      [{"group": "hierarchy", "layers": [{"layer": "hierarchy", "actions": [action]}]}],
    )
    self.assertFalse(action["blocked"], action["blockers"])

  def test_runtime_graph_builds_only_local_event_action_resources(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("event_actions:event_actions:event_action:event_action"),
        template_node(
          "event_actions:event_actions:event_action_iam:iam",
          "event_actions:event_actions:event_action:event_action",
        ),
        template_node(
          "event_actions:event_actions:event_action_lambda:lambda_function",
          "event_actions:event_actions:event_action_iam:iam",
        ),
      ),
    )
    external_event = event("externalAlert", external=True)
    local_event = event("localAlert", external=False)
    local_event_id = resource_names.event_action_id(local_event)

    runtime_graph = build_runtime_graph(
      graph,
      config(),
      [],
      [external_event, local_event],
      [],
    )
    nodes_by_id = runtime_nodes_by_id(runtime_graph)

    self.assertIn(
      f"event_actions:event_actions:event_action:event_action:"
      f"{resource_names.event_action_id(external_event)}",
      nodes_by_id,
    )
    self.assertIn(
      f"event_actions:event_actions:event_action:event_action:{local_event_id}",
      nodes_by_id,
    )
    self.assertIn(
      f"event_actions:event_actions:event_action_iam:iam:{local_event_id}",
      nodes_by_id,
    )
    self.assertIn(
      f"event_actions:event_actions:event_action_lambda:lambda_function:{local_event_id}",
      nodes_by_id,
    )
    self.assertNotIn(
      f"event_actions:event_actions:event_action_iam:iam:"
      f"{resource_names.event_action_id(external_event)}",
      nodes_by_id,
    )
    self.assertEqual(
      "dt-localAlert",
      nodes_by_id[
        f"event_actions:event_actions:event_action_lambda:lambda_function:"
        f"{local_event_id}"
      ].physical_name,
    )

  def test_runtime_graph_rejects_duplicate_runtime_ids(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("hierarchy:hierarchy:twinmaker_hierarchy:twinmaker_hierarchy"),
      ),
    )

    with self.assertRaisesRegex(ValueError, "Duplicate runtime dependency node id"):
      build_runtime_graph(
        graph,
        config(),
        [],
        [],
        [
          {"id": "root-1", "type": "entity", "children": []},
          {"id": "root-1", "type": "entity", "children": []},
        ],
      )

  def test_current_template_json_builds_runtime_graph_for_current_configs(self) -> None:
    graph = load_template_graph(TEMPLATE_PATH)

    runtime_graph = build_runtime_graph(
      graph,
      config(),
      [{"id": "sensor-1", "properties": []}],
      [event("localAlert", external=False)],
      [
        {
          "id": "root-1",
          "type": "entity",
          "children": [
            {
              "type": "component",
              "name": "temperature",
              "iotDeviceId": "sensor-1",
            },
          ],
        },
      ],
    )

    self.assertEqual(graph.version, runtime_graph.version)
    self.assertGreater(len(runtime_graph.nodes), 0)
    self.assertIn(
      "iot:l2:processor_lambda:lambda_function:sensor-1-processor",
      runtime_nodes_by_id(runtime_graph),
    )


def config() -> dict:
  return {"digital_twin_name": "dt"}


def event(function_name: str, external: bool) -> dict:
  return {
    "condition": "root.component.value > 10",
    "action": {
      "type": "lambda",
      "functionName": function_name,
      "external": external,
    },
  }


def runtime_nodes_by_id(runtime_graph):
  return {node.id: node for node in runtime_graph.nodes}


def dependency_ids(runtime_node):
  return [dependency.id for dependency in runtime_node.depends_on]


if __name__ == "__main__":
  unittest.main()
