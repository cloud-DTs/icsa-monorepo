from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import install_aws_stubs

install_aws_stubs()

import deployment_state
import globals
from deployers.aws.apply_actions import ACTION_DEPLOY, ACTION_DESTROY
from deployers.aws.core.grafana_iam_role import GrafanaIamRoleDeployer
from deployers.aws.core.grafana_workspace import GrafanaWorkspaceDeployer
from deployers.aws.core.l5 import L5Deployer
from deployers.aws.core.plan_actions import plan_action


class L5DeployerTests(unittest.TestCase):
  def test_plan_keeps_destroy_actions_only_when_grafana_disabled(self) -> None:
    destroy_role = plan_action("old-grafana", "iam", action=ACTION_DESTROY)
    deploy_role = plan_action("new-grafana", "iam", action=ACTION_DEPLOY)
    no_change_workspace = plan_action("grafana", "grafana_workspace")
    destroy_workspace = plan_action(
      "old-grafana",
      "grafana_workspace",
      action=ACTION_DESTROY,
    )
    deploy_workspace = plan_action(
      "new-grafana",
      "grafana_workspace",
      action=ACTION_DEPLOY,
    )

    with (
      patch("deployers.aws.core.l5.deploy_managed_grafana", False),
      patch.object(
        GrafanaIamRoleDeployer,
        "plan",
        return_value=[destroy_role, deploy_role],
      ),
      patch.object(
        GrafanaWorkspaceDeployer,
        "plan",
        return_value=[
          no_change_workspace,
          destroy_workspace,
          deploy_workspace,
        ],
      ),
    ):
      layer_plan = L5Deployer().plan()

    self.assertEqual("core_l5", layer_plan["layer"])
    self.assertEqual(
      [destroy_role, destroy_workspace],
      layer_plan["actions"],
    )

  def test_plan_keeps_deploy_actions_when_grafana_enabled(self) -> None:
    destroy_role = plan_action("old-grafana", "iam", action=ACTION_DESTROY)
    deploy_role = plan_action("new-grafana", "iam", action=ACTION_DEPLOY)
    destroy_workspace = plan_action(
      "old-grafana",
      "grafana_workspace",
      action=ACTION_DESTROY,
    )
    deploy_workspace = plan_action(
      "new-grafana",
      "grafana_workspace",
      action=ACTION_DEPLOY,
    )

    with (
      patch("deployers.aws.core.l5.deploy_managed_grafana", True),
      patch.object(
        GrafanaIamRoleDeployer,
        "plan",
        return_value=[destroy_role, deploy_role],
      ),
      patch.object(
        GrafanaWorkspaceDeployer,
        "plan",
        return_value=[destroy_workspace, deploy_workspace],
      ),
    ):
      layer_plan = L5Deployer().plan()

    self.assertEqual(
      [destroy_role, deploy_role, destroy_workspace, deploy_workspace],
      layer_plan["actions"],
    )

  def test_deploy_does_not_create_grafana_resources(self) -> None:
    with (
      patch("deployers.aws.core.l5.deploy_managed_grafana", False),
      patch.object(GrafanaIamRoleDeployer, "deploy") as deploy_role,
      patch.object(GrafanaWorkspaceDeployer, "deploy") as deploy_workspace,
    ):
      L5Deployer().deploy()

    deploy_role.assert_not_called()
    deploy_workspace.assert_not_called()

  def test_apply_skips_deploy_actions_when_grafana_disabled(self) -> None:
    role_action = plan_action("dt-grafana", "iam", action=ACTION_DEPLOY)
    workspace_action = plan_action(
      "dt-grafana",
      "grafana_workspace",
      action=ACTION_DEPLOY,
    )
    layer_plan = {
      "layer": "core_l5",
      "actions": [workspace_action, role_action],
    }
    self._patch_grafana_names()

    with (
      patch("deployers.aws.core.l5.deploy_managed_grafana", False),
      patch.object(GrafanaIamRoleDeployer, "apply") as apply_role,
      patch.object(GrafanaWorkspaceDeployer, "apply") as apply_workspace,
      patch.object(deployment_state, "mark_plan_action_processed") as mark,
    ):
      L5Deployer().apply(layer_plan, ACTION_DEPLOY)

    apply_role.assert_not_called()
    apply_workspace.assert_not_called()
    self.assertEqual(2, mark.call_count)

  def test_apply_runs_deploy_actions_when_grafana_enabled(self) -> None:
    role_action = plan_action("dt-grafana", "iam", action=ACTION_DEPLOY)
    workspace_action = plan_action(
      "dt-grafana",
      "grafana_workspace",
      action=ACTION_DEPLOY,
    )
    layer_plan = {
      "layer": "core_l5",
      "actions": [workspace_action, role_action],
    }
    apply_order = []
    self._patch_grafana_names()

    with (
      patch("deployers.aws.core.l5.deploy_managed_grafana", True),
      patch.object(
        GrafanaIamRoleDeployer,
        "apply",
        side_effect=lambda *_: apply_order.append("role"),
      ) as apply_role,
      patch.object(
        GrafanaWorkspaceDeployer,
        "apply",
        side_effect=lambda *_: apply_order.append("workspace"),
      ) as apply_workspace,
      patch.object(deployment_state, "mark_plan_action_processed") as mark,
    ):
      L5Deployer().apply(layer_plan, ACTION_DEPLOY)

    self.assertEqual(["role", "workspace"], apply_order)
    apply_role.assert_called_once_with(role_action, "dt-grafana")
    apply_workspace.assert_called_once_with(workspace_action, "dt-grafana")
    self.assertEqual(
      [
        call("core", "core_l5", role_action),
        call("core", "core_l5", workspace_action),
      ],
      mark.call_args_list,
    )

  def test_apply_keeps_destroy_actions(self) -> None:
    role_action = plan_action("dt-grafana", "iam", action=ACTION_DESTROY)
    workspace_action = plan_action(
      "dt-grafana",
      "grafana_workspace",
      action=ACTION_DESTROY,
    )
    layer_plan = {
      "layer": "core_l5",
      "actions": [role_action, workspace_action],
    }
    apply_order = []
    self._patch_grafana_names()

    with (
      patch.object(
        GrafanaIamRoleDeployer,
        "apply",
        side_effect=lambda *_: apply_order.append("role"),
      ) as apply_role,
      patch.object(
        GrafanaWorkspaceDeployer,
        "apply",
        side_effect=lambda *_: apply_order.append("workspace"),
      ) as apply_workspace,
      patch.object(deployment_state, "mark_plan_action_processed") as mark,
    ):
      L5Deployer().apply(layer_plan, ACTION_DESTROY)

    self.assertEqual(["workspace", "role"], apply_order)
    apply_workspace.assert_called_once_with(workspace_action, "dt-grafana")
    apply_role.assert_called_once_with(role_action, "dt-grafana")
    self.assertEqual(
      [
        call("core", "core_l5", workspace_action),
        call("core", "core_l5", role_action),
      ],
      mark.call_args_list,
    )

  def test_destroy_still_removes_workspace_before_role(self) -> None:
    destroy_order = []

    with (
      patch.object(
        GrafanaWorkspaceDeployer,
        "destroy",
        side_effect=lambda: destroy_order.append("workspace"),
      ),
      patch.object(
        GrafanaIamRoleDeployer,
        "destroy",
        side_effect=lambda: destroy_order.append("role"),
      ),
    ):
      L5Deployer().destroy()

    self.assertEqual(["workspace", "role"], destroy_order)

  def _patch_grafana_names(self) -> None:
    self.enterContext(
      patch.object(
        deployment_state,
        "last_applied_grafana_iam_role_name",
        return_value="dt-grafana",
      )
    )
    self.enterContext(
      patch.object(
        deployment_state,
        "last_applied_grafana_workspace_name",
        return_value="dt-grafana",
      )
    )
    self.enterContext(
      patch.object(
        globals,
        "grafana_iam_role_name",
        return_value="dt-grafana",
      )
    )
    self.enterContext(
      patch.object(
        globals,
        "grafana_workspace_name",
        return_value="dt-grafana",
      )
    )


if __name__ == "__main__":
  unittest.main()
