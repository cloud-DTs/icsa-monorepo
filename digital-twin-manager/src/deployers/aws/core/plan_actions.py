from typing import Any, Literal, NotRequired, TypedDict, Unpack


PlanActionName = Literal[
    # Resource is the same in both desired config and last-applied state.
    # Apply should do nothing for this resource.
    "NO_CHANGE",

    # Resource id exists in desired config, but does not exist in last-applied state.
    # Apply should create/deploy resources for this id.
    "DEPLOY",

    # Update an existing resource without changing its physical identity.
    "UPDATE",

    # Resource id exists in last-applied state, but does not exist in desired config.
    # Apply should destroy resources for this id using last-applied state.
    "DESTROY",
]


PlanResourceType = Literal[
    "dynamodb_table",
    "eventbridge_rule",
    "grafana_workspace",
    "iam",
    "iot_rule",
    "iot_policy",
    "iot_thing",
    "init_value",
    "lambda_function",
    "lambda_permission",
    "s3_bucket",
    "step_function",
    "twinmaker_component_type",
    "twinmaker_hierarchy",
    "twinmaker_workspace",
    "event_action",
]


PLAN_RESOURCE_TYPES: tuple[PlanResourceType, ...] = (
    "dynamodb_table",
    "eventbridge_rule",
    "grafana_workspace",
    "iam",
    "iot_rule",
    "iot_policy",
    "iot_thing",
    "init_value",
    "lambda_function",
    "lambda_permission",
    "s3_bucket",
    "step_function",
    "twinmaker_component_type",
    "twinmaker_hierarchy",
    "twinmaker_workspace",
    "event_action",
)


class PlannedAction(TypedDict):
    resource: Any
    resource_type: PlanResourceType
    graph_id: str | None
    action: PlanActionName
    blocked: bool
    required_flags: list[str]
    blockers: list[str]
    state_sync_required: bool
    processed: bool
    code_sha256: NotRequired[str]
    revision_id: NotRequired[str | None]
    lambda_function_name: NotRequired[str]
    lambda_configuration: NotRequired[dict]
    aws_configuration: NotRequired[dict]
    policy_document: NotRequired[dict | None]
    aws_policy_document: NotRequired[dict | None]
    aws_policy_snapshot: NotRequired[dict | None]
    delete_policy_version_id: NotRequired[str | None]
    component_device_bindings: NotRequired[list[dict]]
    topic_rule_payload: NotRequired[dict]
    aws_topic_rule_payload: NotRequired[dict | None]


class PlannedActionValues(TypedDict, total=False):
    graph_id: str | None
    action: PlanActionName
    blocked: bool
    required_flags: list[str]
    blockers: list[str]
    state_sync_required: bool
    region: str
    code_sha256: str
    revision_id: str | None
    lambda_function_name: str
    lambda_configuration: dict
    aws_configuration: dict
    policy_document: dict | None
    aws_policy_document: dict | None
    aws_policy_snapshot: dict | None
    delete_policy_version_id: str | None
    component_device_bindings: list[dict]
    topic_rule_payload: dict
    aws_topic_rule_payload: dict | None


def plan_action(
    resource: Any,
    resource_type: PlanResourceType,
    **values: Unpack[PlannedActionValues],
) -> PlannedAction:
    action: PlannedAction = {
        "resource": resource,
        "resource_type": resource_type,
        "graph_id": None,
        "action": "NO_CHANGE",
        "blocked": False,
        "required_flags": [],
        "blockers": [],
        "state_sync_required": False,
        "processed": False,
    }

    action.update(values)
    return action

def sort_actions_for_apply(
    actions: list[PlannedAction],
    destroy_order: dict[PlanResourceType, int],
    deploy_order: dict[PlanResourceType, int],
) -> list[PlannedAction]:
    destroy_actions = [
        action for action in actions
        if action["action"] == "DESTROY"
    ]
    deploy_actions = [
        action for action in actions
        if action["action"] in ("DEPLOY", "UPDATE")
    ]

    destroy_actions.sort(
        key=lambda action: destroy_order[action["resource_type"]]
    )
    deploy_actions.sort(
        key=lambda action: deploy_order[action["resource_type"]]
    )

    return destroy_actions + deploy_actions
