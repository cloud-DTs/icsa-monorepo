import deployment_state
import globals
from deployers.aws.apply_actions import (
    ACTION_DEPLOY,
    ACTION_DESTROY,
    pending_actions,
)
from deployers.aws.core.grafana_iam_role import GrafanaIamRoleDeployer
from deployers.aws.core.grafana_workspace import GrafanaWorkspaceDeployer
from deployers.aws.core.plan_actions import sort_actions_for_apply
from deployers.base import Deployer
from globals import deploy_managed_grafana


class L5Deployer(Deployer):
    DESTROY_ORDER = {
        "grafana_workspace": 0,
        "iam": 1,
    }

    DEPLOY_ORDER = {
        "iam": 0,
        "grafana_workspace": 1,
    }

    def log(self, message):
        print(message)

    def plan(self):
        grafana_actions = [
            *GrafanaIamRoleDeployer().plan(),
            *GrafanaWorkspaceDeployer().plan(),
        ]
        actions = grafana_actions
        if not deploy_managed_grafana:
            # Cleanup actions keep TwinMaker replacement valid in the dependency graph.
            actions = [
                action
                for action in grafana_actions
                if action["action"] == ACTION_DESTROY
            ]

        return {
            "layer": "core_l5",
            "actions": actions,
        }

    def sort_actions_for_apply(self, actions):
        return sort_actions_for_apply(
            actions,
            self.DESTROY_ORDER,
            self.DEPLOY_ORDER,
        )

    def apply(self, layer_plan, action_name):
        layer_name = layer_plan["layer"]
        actions = pending_actions(layer_plan["actions"], action_name)

        if not actions:
            return

        actions = self.sort_actions_for_apply(actions)

        for action in actions:
            resource_type = action["resource_type"]
            resource = action["resource"]

            is_grafana_iam_role = resource_type == "iam" and resource in [
                deployment_state.last_applied_grafana_iam_role_name(),
                globals.grafana_iam_role_name(),
            ]
            is_grafana_workspace = (
                resource_type == "grafana_workspace"
                and resource
                in [
                    deployment_state.last_applied_grafana_workspace_name(),
                    globals.grafana_workspace_name(),
                ]
            )

            if (
                action_name == ACTION_DEPLOY
                and (is_grafana_iam_role or is_grafana_workspace)
                and not deploy_managed_grafana
            ):
                self.log(
                    f"Skipping disabled Grafana deployment: {resource_type}/{resource}"
                )
            elif is_grafana_iam_role:
                GrafanaIamRoleDeployer().apply(action, resource)
            elif is_grafana_workspace:
                GrafanaWorkspaceDeployer().apply(action, resource)
            else:
                raise ValueError(
                    f"No core_l5 apply handler for {resource_type}/{resource}"
                )

            deployment_state.mark_plan_action_processed("core", layer_name, action)

    def deploy(self):
        if deploy_managed_grafana:
            GrafanaIamRoleDeployer().deploy()
            GrafanaWorkspaceDeployer().deploy()
        else:
            self.log(
                "Managed Grafana deployment is disabled. Set DEPLOY_MANAGED_GRAFANA=true to enable deployment."
            )

    def destroy(self):
        GrafanaWorkspaceDeployer().destroy()
        GrafanaIamRoleDeployer().destroy()

    def info(self):
        GrafanaIamRoleDeployer().info()
        GrafanaWorkspaceDeployer().info()
