from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deployers.aws.apply_actions import pending_actions
from deployers.aws.core.plan_actions import plan_action, sort_actions_for_apply
from dependency_graph.dependency_analyzer import analyze_plan_dependencies
from dependency_graph.models import DependencyType, RuntimeDependency, RuntimeGraph, RuntimeNode


def node(name, *dependencies, physical_name=None):
  return RuntimeNode(
    id=name, template_id=name, owner_deployer="TestDeployer", logical_name=name,
    physical_name=physical_name or name,
    depends_on=tuple(
      RuntimeDependency(id=dependency, template_id=dependency, type=DependencyType.CREATE_AFTER)
      for dependency in dependencies
    ),
  )


def graph(*nodes):
  return RuntimeGraph(version=1, nodes=nodes)


def plan(*actions):
  return [{"group": "test", "layers": [{"layer": "test", "actions": list(actions)}]}]


class UpdateActionTests(unittest.TestCase):
  def test_forward_apply_phase_orders_policy_update_before_lambda_update(self):
    code = plan_action("reader", "lambda_function", action="UPDATE")
    policy = plan_action("role", "iam", action="UPDATE")
    skipped = plan_action("other", "iam", action="UPDATE", blocked=True)

    pending = pending_actions([code, skipped, policy], "DEPLOY")
    ordered = sort_actions_for_apply(pending, {"iam": 1, "lambda_function": 0}, {"iam": 0, "lambda_function": 1})

    self.assertEqual([policy, code], ordered)
    self.assertEqual([], pending_actions([code, policy], "DESTROY"))

  def test_update_of_unchanged_identity_does_not_require_destroying_dependents(self):
    previous = graph(node("reader"), node("type", "reader"))
    update = plan_action("reader", "lambda_function", action="UPDATE", graph_id="reader")

    analyze_plan_dependencies(previous, previous, plan(update))

    self.assertFalse(update["blocked"])

  def test_update_blocks_when_target_does_not_exist_in_previous_graph(self):
    update = plan_action("reader", "lambda_function", action="UPDATE", graph_id="reader")

    analyze_plan_dependencies(graph(), graph(node("reader")), plan(update))

    self.assertTrue(update["blocked"])

  def test_update_blocks_a_physical_rename(self):
    update = plan_action("new-reader", "lambda_function", action="UPDATE", graph_id="reader")

    analyze_plan_dependencies(
      graph(node("reader", physical_name="old-reader")),
      graph(node("reader", physical_name="new-reader")), plan(update),
    )

    self.assertTrue(update["blocked"])

  def test_failed_update_prerequisite_blocks_component_type_creation(self):
    previous = graph(node("role"), node("reader", "role"))
    desired = graph(node("reader", "role"), node("type", "reader"))
    update = plan_action("reader", "lambda_function", action="UPDATE", graph_id="reader")
    create_type = plan_action("type", "twinmaker_component_type", action="DEPLOY", graph_id="type")

    analyze_plan_dependencies(previous, desired, plan(update, create_type))

    self.assertTrue(update["blocked"])
    self.assertTrue(create_type["blocked"])


if __name__ == "__main__":
  unittest.main()
