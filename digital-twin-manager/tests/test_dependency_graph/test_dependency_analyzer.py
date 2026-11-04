from __future__ import annotations
import unittest

from dependency_graph_helpers import ensure_src_path

ensure_src_path()

from dependency_graph.dependency_analyzer import analyze_plan_dependencies
from dependency_graph.models import (
  DependencyType,
  RuntimeDependency,
  RuntimeGraph,
  RuntimeNode,
)
from deployers.aws.core.plan_actions import PlannedAction, plan_action


class DependencyAnalyzerTests(unittest.TestCase):
  def test_deploy_blocks_when_prerequisite_is_missing_from_desired_graph(self) -> None:
    desired_graph = runtime_graph(
      runtime_node(
        "runtime:node:a",
        runtime_dependency("runtime:node:b"),
      ),
    )
    plan_groups = plan_with_actions([
      plan_action("a", "lambda_function", action="DEPLOY", graph_id="runtime:node:a"),
    ])

    analyze_plan_dependencies(runtime_graph(), desired_graph, plan_groups)

    action = only_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertIn("prerequisite runtime:node:b", action["blockers"][0])

  def test_deploy_blocks_when_graph_id_is_missing(self) -> None:
    desired_graph = runtime_graph(runtime_node("runtime:node:a"))
    plan_groups = plan_with_actions([
      plan_action("a", "lambda_function", action="DEPLOY"),
    ])

    analyze_plan_dependencies(runtime_graph(), desired_graph, plan_groups)

    action = only_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertEqual(
      ["Cannot analyze DEPLOY dependencies because graph_id is missing."],
      action["blockers"],
    )

  def test_deploy_blocks_when_action_node_is_missing_from_desired_graph(self) -> None:
    plan_groups = plan_with_actions([
      plan_action("a", "lambda_function", action="DEPLOY", graph_id="runtime:node:a"),
    ])

    analyze_plan_dependencies(runtime_graph(), runtime_graph(), plan_groups)

    action = only_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertEqual(
      ["Cannot deploy runtime:node:a because it is missing from desired graph."],
      action["blockers"],
    )

  def test_deploy_allows_existing_prerequisite_in_desired_graph(self) -> None:
    desired_graph = runtime_graph(
      runtime_node(
        "runtime:node:a",
        runtime_dependency("runtime:node:b"),
      ),
      runtime_node("runtime:node:b"),
    )
    plan_groups = plan_with_actions([
      plan_action("a", "lambda_function", action="DEPLOY", graph_id="runtime:node:a"),
    ])

    analyze_plan_dependencies(runtime_graph(), desired_graph, plan_groups)

    self.assertFalse(only_action(plan_groups)["blocked"])

  def test_deploy_ignores_blocks_delete_dependencies(self) -> None:
    desired_graph = runtime_graph(
      runtime_node(
        "runtime:node:a",
        runtime_dependency(
          "runtime:node:b",
          dependency_type=DependencyType.BLOCKS_DELETE,
        ),
      ),
    )
    plan_groups = plan_with_actions([
      plan_action("a", "lambda_function", action="DEPLOY", graph_id="runtime:node:a"),
    ])

    analyze_plan_dependencies(runtime_graph(), desired_graph, plan_groups)

    self.assertFalse(only_action(plan_groups)["blocked"])

  def test_deploy_propagates_analyzer_created_prerequisite_blocker(self) -> None:
    desired_graph = runtime_graph(
      runtime_node(
        "runtime:node:a",
        runtime_dependency("runtime:node:b"),
      ),
      runtime_node(
        "runtime:node:b",
        runtime_dependency("runtime:node:c"),
      ),
    )
    plan_groups = plan_with_actions([
      plan_action("a", "lambda_function", action="DEPLOY", graph_id="runtime:node:a"),
      plan_action("b", "iam", action="DEPLOY", graph_id="runtime:node:b"),
    ])

    analyze_plan_dependencies(runtime_graph(), desired_graph, plan_groups)

    action_a, action_b = actions(plan_groups)
    self.assertTrue(action_b["blocked"])
    self.assertIn("prerequisite runtime:node:c", action_b["blockers"][0])
    self.assertTrue(action_a["blocked"])
    self.assertIn("runtime:node:b is blocked", action_a["blockers"][0])

  def test_destroy_blocks_when_dependent_still_depends_in_desired_graph(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependent",
        "lambda_function",
        graph_id="runtime:node:dependent",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    action = first_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertIn("runtime:node:dependent still depends on it", action["blockers"][0])

  def test_destroy_blocks_when_graph_id_is_missing(self) -> None:
    previous_graph = runtime_graph(runtime_node("runtime:node:dependency"))
    plan_groups = plan_with_actions([
      plan_action("dependency", "iam", action="DESTROY"),
    ])

    analyze_plan_dependencies(previous_graph, runtime_graph(), plan_groups)

    action = only_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertEqual(
      ["Cannot analyze DESTROY dependencies because graph_id is missing."],
      action["blockers"],
    )

  def test_destroy_blocks_when_action_node_is_missing_from_previous_graph(self) -> None:
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
    ])

    analyze_plan_dependencies(runtime_graph(), runtime_graph(), plan_groups)

    action = only_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertEqual(
      [
        "Cannot destroy runtime:node:dependency because it is missing "
        "from previous graph."
      ],
      action["blockers"],
    )

  def test_destroy_allows_dependent_that_is_also_destroyed(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependent",
        "lambda_function",
        action="DESTROY",
        graph_id="runtime:node:dependent",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_blocks_replacement_dependency_with_no_change_dependent(self) -> None:
    previous_graph = runtime_graph(
      runtime_node(
        "runtime:node:dependency",
        owner_deployer="DependencyDeployer",
        physical_name="old-dependency",
      ),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node(
        "runtime:node:dependency",
        owner_deployer="DependencyDeployer",
        physical_name="new-dependency",
      ),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependency",
        "iam",
        action="DEPLOY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependent",
        "lambda_function",
        graph_id="runtime:node:dependent",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    action = first_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertIn("runtime:node:dependent still depends on it", action["blockers"][0])

  def test_destroy_allows_replacement_dependency_with_same_physical_name(self) -> None:
    previous_graph = runtime_graph(
      runtime_node(
        "runtime:node:dependency",
        owner_deployer="DependencyDeployer",
        physical_name="same-dependency",
      ),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node(
        "runtime:node:dependency",
        owner_deployer="DependencyDeployer",
        physical_name="same-dependency",
      ),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependency",
        "iam",
        action="DEPLOY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependent",
        "lambda_function",
        graph_id="runtime:node:dependent",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_allows_replacement_dependency_when_dependent_is_redeployed(
    self,
  ) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependency",
        "iam",
        action="DEPLOY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependent",
        "lambda_function",
        action="DEPLOY",
        graph_id="runtime:node:dependent",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_blocks_when_replacement_deploy_is_blocked(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependency",
        "iam",
        action="DEPLOY",
        graph_id="runtime:node:dependency",
        blocked=True,
        blockers=["replacement deploy is blocked"],
      ),
      plan_action(
        "dependent",
        "lambda_function",
        graph_id="runtime:node:dependent",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    action = first_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertIn("still depends on it", action["blockers"][0])

  def test_destroy_allows_dependent_removed_from_desired_graph(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
      ),
    )
    desired_graph = runtime_graph(runtime_node("runtime:node:dependency"))
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_allows_dependent_that_no_longer_depends_in_desired_graph(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency"),
      runtime_node("runtime:node:dependent"),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_blocks_when_dependent_destroy_action_is_blocked(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "dependent",
        "lambda_function",
        action="DESTROY",
        graph_id="runtime:node:dependent",
        blocked=True,
        blockers=["dependent cannot be destroyed"],
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    action = first_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertIn("dependent cannot be destroyed", action["blockers"][0])

  def test_deploy_blocks_when_prerequisite_deploy_action_is_blocked(self) -> None:
    desired_graph = runtime_graph(
      runtime_node(
        "runtime:node:a",
        runtime_dependency("runtime:node:b"),
      ),
      runtime_node("runtime:node:b"),
    )
    plan_groups = plan_with_actions([
      plan_action("a", "lambda_function", action="DEPLOY", graph_id="runtime:node:a"),
      plan_action(
        "b",
        "iam",
        action="DEPLOY",
        graph_id="runtime:node:b",
        blocked=True,
        blockers=["pre-existing blocker"],
      ),
    ])

    analyze_plan_dependencies(runtime_graph(), desired_graph, plan_groups)

    action = first_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertIn("pre-existing blocker", action["blockers"][0])

  def test_destroy_blocks_dependent_without_plan_action(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="DependentDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    action = first_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertIn("has no plan action", action["blockers"][0])

  def test_destroy_ignores_same_owner_dependent_without_plan_action(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="SharedDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="SharedDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="SharedDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="SharedDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_ignores_lifecycle_artifact_without_plan_action(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:cleanup",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="CleanupDeployer",
        lifecycle_artifact=True,
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:cleanup",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="CleanupDeployer",
        lifecycle_artifact=True,
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_ignores_lifecycle_artifact_with_no_change_action(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:cleanup",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="CleanupDeployer",
        lifecycle_artifact=True,
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node(
        "runtime:node:cleanup",
        runtime_dependency("runtime:node:dependency"),
        owner_deployer="CleanupDeployer",
        lifecycle_artifact=True,
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "cleanup",
        "lambda_function",
        graph_id="runtime:node:cleanup",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_ignores_dependent_covered_by_owner_destroy_action(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node("runtime:node:root", owner_deployer="DependentDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        runtime_dependency("runtime:node:root"),
        owner_deployer="DependentDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node("runtime:node:root", owner_deployer="DependentDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        runtime_dependency("runtime:node:root"),
        owner_deployer="DependentDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "root",
        "twinmaker_hierarchy",
        action="DESTROY",
        graph_id="runtime:node:root",
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    self.assertFalse(first_action(plan_groups)["blocked"])

  def test_destroy_blocks_when_owner_destroy_coverage_is_blocked(self) -> None:
    previous_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node("runtime:node:root", owner_deployer="DependentDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        runtime_dependency("runtime:node:root"),
        owner_deployer="DependentDeployer",
      ),
    )
    desired_graph = runtime_graph(
      runtime_node("runtime:node:dependency", owner_deployer="DependencyDeployer"),
      runtime_node("runtime:node:root", owner_deployer="DependentDeployer"),
      runtime_node(
        "runtime:node:dependent",
        runtime_dependency("runtime:node:dependency"),
        runtime_dependency("runtime:node:root"),
        owner_deployer="DependentDeployer",
      ),
    )
    plan_groups = plan_with_actions([
      plan_action(
        "dependency",
        "iam",
        action="DESTROY",
        graph_id="runtime:node:dependency",
      ),
      plan_action(
        "root",
        "twinmaker_hierarchy",
        action="DESTROY",
        graph_id="runtime:node:root",
        blocked=True,
        blockers=["root destroy is blocked"],
      ),
    ])

    analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

    action = first_action(plan_groups)
    self.assertTrue(action["blocked"])
    self.assertIn("has no plan action", action["blockers"][0])

  def test_analyzer_does_not_duplicate_existing_blockers(self) -> None:
    desired_graph = runtime_graph(
      runtime_node(
        "runtime:node:a",
        runtime_dependency("runtime:node:b"),
      ),
    )
    plan_groups = plan_with_actions([
      plan_action("a", "lambda_function", action="DEPLOY", graph_id="runtime:node:a"),
    ])

    analyze_plan_dependencies(runtime_graph(), desired_graph, plan_groups)
    analyze_plan_dependencies(runtime_graph(), desired_graph, plan_groups)

    self.assertEqual(1, len(only_action(plan_groups)["blockers"]))


def runtime_graph(*nodes: RuntimeNode) -> RuntimeGraph:
  return RuntimeGraph(version=1, nodes=nodes)


def runtime_node(
  node_id: str,
  *dependencies: RuntimeDependency,
  owner_deployer: str = "TestDeployer",
  physical_name: str | None = None,
  lifecycle_artifact: bool = False,
) -> RuntimeNode:
  return RuntimeNode(
    id=node_id,
    template_id=node_id.rsplit(":", 1)[0],
    owner_deployer=owner_deployer,
    logical_name=node_id.rsplit(":", 1)[-1],
    physical_name=physical_name or node_id,
    depends_on=dependencies,
    lifecycle_artifact=lifecycle_artifact,
  )


def runtime_dependency(
  node_id: str,
  dependency_type: DependencyType = DependencyType.CREATE_AFTER,
) -> RuntimeDependency:
  return RuntimeDependency(
    id=node_id,
    template_id=node_id.rsplit(":", 1)[0],
    type=dependency_type,
  )


def plan_with_actions(actions: list[PlannedAction]) -> list[dict]:
  return [
    {
      "group": "test",
      "layers": [
        {
          "layer": "test",
          "actions": actions,
        }
      ],
    }
  ]


def first_action(plan_groups: list[dict]) -> dict:
  return plan_groups[0]["layers"][0]["actions"][0]


def actions(plan_groups: list[dict]) -> list[dict]:
  return plan_groups[0]["layers"][0]["actions"]


def only_action(plan_groups: list[dict]) -> dict:
  plan_actions = actions(plan_groups)
  assert len(plan_actions) == 1
  return plan_actions[0]


if __name__ == "__main__":
  unittest.main()
