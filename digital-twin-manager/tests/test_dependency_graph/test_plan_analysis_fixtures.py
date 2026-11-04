from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path

from dependency_graph_helpers import ensure_src_path
from tests.aws_stubs import AWS_REGION, StubAwsClient, StubStsClient, install_aws_stubs


ensure_src_path()
install_aws_stubs()


import deployment_state
import deployers.aws.core.all
import deployers.aws.event_actions.all
import deployers.aws.hierarchy.all
import deployers.aws.init_values.all
import deployers.aws.iot.all
import globals
import resource_names
import main
import util
from deployers.aws.core.hot_reader_iam_role import HotReaderIamRoleDeployer
from deployers.aws.core.event_feedback_iam_role import EventFeedbackIamRoleDeployer
from deployers.aws.core.event_checker_iam_role import EventCheckerIamRoleDeployer
from deployers.aws.core.cold_archive_mover_iam_role import ColdArchiveMoverIamRoleDeployer
from deployers.aws.core.twinmaker_s3_bucket import TwinmakerS3BucketDeployer
from deployers.aws.core.hot_reader_lambda_function import HotReaderLambdaFunctionDeployer
from deployers.aws.iot.device_reconciliation import desired_iot_devices
from deployers.aws.iot.device_config import effective_iot_devices
from deployers.aws.iot.processor_lambda_function import ProcessorLambdaFunctionDeployer
from deployers.aws.iot.policy_document import policy_document
from deployers.aws.event_actions.lambda_actions import LambdaActionsDeployer
from botocore.exceptions import ClientError
from dependency_graph.dependency_analyzer import analyze_plan_dependencies
from dependency_graph import plan_graph_ids
from dependency_graph.models import (
  DependencyType,
  RuntimeDependency,
  RuntimeGraph,
  RuntimeNode,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_ANALYSIS_CONFIGS_DIR = REPO_ROOT / "configs" / "plan-analysis"
CONFIG_CASES_DIR = PLAN_ANALYSIS_CONFIGS_DIR / "config-cases"
SYNTHETIC_BLOCKERS_DIR = PLAN_ANALYSIS_CONFIGS_DIR / "synthetic-blockers"

CONFIG_CASES_WITH_NO_BLOCKERS = [
  ("no-change", {"DESTROY": 0, "DEPLOY": 0, "UPDATE": 0}),
  ("full-replacement", {"DESTROY": "present", "DEPLOY": "present"}),
  ("added-iot-device", {"DEPLOY": "present"}),
  ("removed-iot-device", {"DESTROY": "present"}),
  ("removed-hierarchy-entity-component", {"DESTROY": "present", "DEPLOY": "present"}),
  ("changed-event-action", {"DESTROY": "present", "DEPLOY": "present"}),
  ("removed-event-action", {"DESTROY": "present", "DEPLOY": 0, "UPDATE": "present"}),
  ("init-values-changed", {"DESTROY": 0, "DEPLOY": "present"}),
]

SYNTHETIC_BLOCKER_CASES = [
  ("missing-prerequisite-deploy", "missing from desired graph"),
  ("reverse-dependent-destroy", "still depends on it"),
]


class FixtureS3Client(StubAwsClient):
  def get_bucket_policy(self, **kwargs):
    return {"Policy": json.dumps(self.policy_document)}


class PlanAnalysisConfigFixtureTests(unittest.TestCase):
  def test_config_cases_have_expected_plan_actions_without_blockers(self) -> None:
    for case_name, expected_counts in CONFIG_CASES_WITH_NO_BLOCKERS:
      with self.subTest(case_name=case_name):
        load_plan_analysis_case(case_name)

        with redirect_stdout(StringIO()):
          plan_groups = build_plan_groups()

        counts_before_analysis = action_counts(plan_groups)

        main._analyze_plan_dependencies(plan_groups)

        assert_expected_counts(self, counts_before_analysis, expected_counts)
        self.assertEqual([], blocked_action_summaries(plan_groups))

  def test_shared_component_type_is_deployed_once(self) -> None:
    load_plan_analysis_case("shared-component-type")

    with redirect_stdout(StringIO()):
      plan_groups = build_plan_groups()

    main._analyze_plan_dependencies(plan_groups)

    self.assertEqual([], blocked_action_summaries(plan_groups))

    component_type_deploys = [
      action
      for _, layer_name, action in iter_plan_actions(plan_groups)
      if layer_name == "iot_l4"
      and action["resource_type"] == "twinmaker_component_type"
      and action["action"] == "DEPLOY"
    ]

    self.assertEqual(
      1,
      len(component_type_deploys),
      "Two IoT devices sharing one componentTypeId should deploy a single "
      f"TwinMaker Component Type, got: {component_type_deploys}",
    )

  def test_event_checker_missing_workspace_permission_is_an_unblocked_policy_update(self) -> None:
    load_plan_analysis_case("no-change")
    document = globals.aws_iam_client.checker_policy_document
    document["Statement"] = [
      statement for statement in document["Statement"]
      if statement["Action"] != "iottwinmaker:GetWorkspace"
    ]
    with redirect_stdout(StringIO()):
      plan_groups = build_plan_groups()
    main._analyze_plan_dependencies(plan_groups)
    self.assertEqual([], blocked_action_summaries(plan_groups))
    checker_actions = [
      action for _, _, action in iter_plan_actions(plan_groups)
      if action.get("graph_id") == plan_graph_ids.EVENT_CHECKER_IAM
    ]
    self.assertEqual(["UPDATE"], [action["action"] for action in checker_actions])
    self.assertEqual(globals.event_checker_iam_role_name(), checker_actions[0]["resource"])

  def test_synthetic_blocker_cases_have_expected_blockers(self) -> None:
    for case_name, blocker_text in SYNTHETIC_BLOCKER_CASES:
      with self.subTest(case_name=case_name):
        previous_graph, desired_graph, plan_groups = load_synthetic_blocker_case(
          case_name
        )

        analyze_plan_dependencies(previous_graph, desired_graph, plan_groups)

        blocked_summaries = blocked_action_summaries(plan_groups)
        self.assertEqual(1, len(blocked_summaries))
        self.assertIn(blocker_text, blocked_summaries[0])

  def test_shared_component_type_transition_updates_old_hot_reader(self) -> None:
    load_plan_analysis_case("shared-component-type")
    globals.aws_lambda_client.functions[globals.hot_reader_lambda_function_name()]["CodeSha256"] = util.lambda_code_sha256(b"legacy package")
    globals.aws_iam_client.policy_document["Statement"][1]["Action"] = [
      "iottwinmaker:GetEntity",
    ]

    with redirect_stdout(StringIO()):
      plan_groups = build_plan_groups()
    main._analyze_plan_dependencies(plan_groups)

    self.assertEqual([], blocked_action_summaries(plan_groups))
    hot_reader_actions = [
      action for _, _, action in iter_plan_actions(plan_groups)
      if action.get("graph_id") in (plan_graph_ids.HOT_READER_LAMBDA, plan_graph_ids.HOT_READER_IAM)
    ]
    self.assertEqual(2, len(hot_reader_actions))
    self.assertEqual(["UPDATE", "UPDATE"], [action["action"] for action in hot_reader_actions])


def assert_expected_counts(
  test_case: unittest.TestCase,
  counts: dict[str, int],
  expected_counts: dict[str, int | str],
) -> None:
  for action_name, expectation in expected_counts.items():
    if expectation == "present":
      test_case.assertGreater(counts[action_name], 0)
    else:
      test_case.assertEqual(expectation, counts[action_name])


def load_plan_analysis_case(case_name: str) -> None:
  case_dir = CONFIG_CASES_DIR / case_name
  previous_configs = read_config_set(case_dir / "previous")
  desired_configs = read_config_set(case_dir / "desired")

  globals.config = desired_configs["config"]
  globals.config_iot_devices = desired_configs["config_iot_devices"]
  globals.config_events = desired_configs["config_events"]
  globals.config_hierarchy = desired_configs["config_hierarchy"]

  deployment_state.last_applied_config = previous_configs["config"]
  deployment_state.last_applied_config_iot_devices = (
    previous_configs["config_iot_devices"]
  )
  deployment_state.last_applied_config_events = previous_configs["config_events"]
  deployment_state.last_applied_config_hierarchy = (
    previous_configs["config_hierarchy"]
  )
  deployment_state.last_applied_state_metadata = {"awsRegion": AWS_REGION}

  globals.aws_s3_client = FixtureS3Client()
  globals.aws_twinmaker_client = StubAwsClient()
  globals.aws_sf_client = StubAwsClient()
  globals.aws_grafana_client = StubAwsClient()
  globals.aws_lambda_client = FixtureLambdaClient()
  globals.aws_iot_client = FixtureIotClient(previous_configs)
  globals.aws_sts_client = StubStsClient()
  globals.aws_dynamodb_client = StubAwsClient()
  globals.aws_iam_client = FixtureIamClient()

  # AWS retains the previously deployed packages and settings while desired config changes.
  for name, value in previous_configs.items():
    setattr(globals, name, value)
  try:
    globals.aws_s3_client.policy_document = TwinmakerS3BucketDeployer()._desired_policy_document(
      globals.twinmaker_s3_bucket_name(),
    )
    globals.aws_iam_client.feedback_policy_document = EventFeedbackIamRoleDeployer()._desired_policy_document()
    globals.aws_iam_client.checker_policy_document = EventCheckerIamRoleDeployer()._desired_policy_document()
    globals.aws_iam_client.cold_archive_policy_document = ColdArchiveMoverIamRoleDeployer()._desired_policy_document()
    for deployer_class in deployers.aws.core.all.AllDeployer.LAMBDA_DEPLOYERS.values():
      globals.aws_lambda_client.add_function(deployer_class()._lambda_definition())
    for iot_device in desired_iot_devices():
      globals.aws_lambda_client.add_function(ProcessorLambdaFunctionDeployer()._lambda_definition(iot_device))
    for event in globals.config_events:
      definition = LambdaActionsDeployer()._lambda_definition(event)
      if definition is not None:
        globals.aws_lambda_client.add_function(definition)
    dispatcher = globals.dispatcher_lambda_function_name()
    globals.aws_lambda_client.policies[dispatcher] = {"Statement": [{
      "Sid": "iot-invoke",
      "Effect": "Allow",
      "Principal": {"Service": "iot.amazonaws.com"},
      "Action": "lambda:InvokeFunction",
      "Resource": f"arn:aws:lambda:{AWS_REGION}:123456789012:function:{dispatcher}",
      "Condition": {"ArnLike": {
        "AWS:SourceArn": f"arn:aws:iot:{AWS_REGION}:123456789012:rule/{globals.dispatcher_iot_rule_name()}",
      }},
    }]}
  finally:
    for name, value in desired_configs.items():
      setattr(globals, name, value)


class FixtureIotClient(StubAwsClient):
  def __init__(self, configs):
    super().__init__()
    self.config = configs["config"]
    self.policy_name = resource_names.iot_policy_name(configs["config"])
    self.policy_document = policy_document(configs["config"], configs["config_events"], f"arn:aws:iot:{AWS_REGION}:123456789012")
    self.principals = {
      resource_names.iot_thing_name(configs["config"], device):
        f"arn:aws:iot:{AWS_REGION}:123456789012:cert/{device['id']}"
      for device in effective_iot_devices(configs["config_iot_devices"])
    }

  def get_topic_rule(self, ruleName):
    if ruleName != resource_names.dispatcher_iot_rule_name(self.config):
      raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetTopicRule")
    topic = resource_names.dispatcher_iot_rule_topic(self.config)
    function = resource_names.dispatcher_lambda_function_name(self.config)
    fields = "*, timestamp() AS iot_ingested_at_ms" if globals.debug else "*"
    return {"rule": {
      "sql": f"SELECT {fields} FROM '{topic}'",
      "description": "",
      "actions": [{"lambda": {
        "functionArn": f"arn:aws:lambda:{AWS_REGION}:123456789012:function:{function}",
      }}],
      "ruleDisabled": False,
    }}

  def get_policy(self, policyName):
    if policyName != self.policy_name:
      raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetPolicy")
    return {
      "policyName": policyName,
      "policyArn": f"arn:aws:iot:{AWS_REGION}:123456789012:policy/{policyName}",
      "defaultVersionId": "1",
      "policyDocument": json.dumps(self.policy_document),
    }

  def list_policy_versions(self, policyName):
    self.get_policy(policyName=policyName)
    return {"policyVersions": [{"versionId": "1", "isDefaultVersion": True}]}

  def list_thing_principals(self, thingName):
    if thingName not in self.principals:
      raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "ListThingPrincipals")
    return {"principals": [self.principals[thingName]]}

  def list_attached_policies(self, target):
    return {"policies": [{"policyName": self.policy_name}]}

  def list_targets_for_policy(self, policyName, **kwargs):
    self.get_policy(policyName=policyName)
    return {"targets": list(self.principals.values())}


class FixtureLambdaClient(StubAwsClient):
  def __init__(self):
    super().__init__()
    self.functions = {}
    self.policies = {}

  def get_policy(self, FunctionName):
    if FunctionName not in self.policies:
      raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetPolicy")
    return {"Policy": json.dumps(self.policies[FunctionName])}

  def add_function(self, definition):
    self.functions[definition.function_name] = {
      **definition.configuration(),
      "CodeSha256": util.lambda_code_sha256(definition.package()),
      "RevisionId": "fixture-revision",
      "State": "Active",
      "LastUpdateStatus": "Successful",
    }

  def get_function(self, **kwargs):
    configuration = self.functions.get(kwargs["FunctionName"])
    if configuration is None:
      raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetFunction")
    return {"Configuration": deepcopy(configuration)}


class FixtureIamClient(StubAwsClient):
  def __init__(self):
    super().__init__()
    self.policy_document = HotReaderIamRoleDeployer()._desired_policy_document()
    self.feedback_policy_document = None
    self.checker_policy_document = None
    self.cold_archive_policy_document = None

  def get_role(self, **kwargs):
    return {"Role": {"Arn": f"arn:aws:iam::123456789012:role/{kwargs['RoleName']}"}}

  def get_role_policy(self, **kwargs):
    if kwargs["PolicyName"] == HotReaderIamRoleDeployer.POLICY_NAME:
      document = self.policy_document
    elif kwargs["PolicyName"] == EventFeedbackIamRoleDeployer.POLICY_NAME:
      document = self.feedback_policy_document
    elif kwargs["PolicyName"] == EventCheckerIamRoleDeployer.POLICY_NAME:
      document = self.checker_policy_document
    elif kwargs["PolicyName"] == ColdArchiveMoverIamRoleDeployer.POLICY_NAME:
      document = self.cold_archive_policy_document
    else:
      document = None
    if document is None:
      raise ClientError({"Error": {"Code": "NoSuchEntity"}}, "GetRolePolicy")
    return {"PolicyDocument": deepcopy(document)}


def read_config_set(config_dir: Path) -> dict:
  return {
    "config": read_json(config_dir / "config.json"),
    "config_events": read_json(config_dir / "config_events.json"),
    "config_hierarchy": read_json(config_dir / "config_hierarchy.json"),
    "config_iot_devices": read_json(config_dir / "config_iot_devices.json"),
  }


def load_synthetic_blocker_case(
  case_name: str,
) -> tuple[RuntimeGraph, RuntimeGraph, list[dict]]:
  case_dir = SYNTHETIC_BLOCKERS_DIR / case_name

  return (
    parse_runtime_graph(read_json(case_dir / "previous_graph.json")),
    parse_runtime_graph(read_json(case_dir / "desired_graph.json")),
    read_json(case_dir / "plan_groups.json"),
  )


def parse_runtime_graph(value: dict) -> RuntimeGraph:
  return RuntimeGraph(
    version=value["version"],
    nodes=tuple(parse_runtime_node(node) for node in value["nodes"]),
  )


def parse_runtime_node(value: dict) -> RuntimeNode:
  return RuntimeNode(
    id=value["id"],
    template_id=value["template_id"],
    owner_deployer=value["owner_deployer"],
    logical_name=value["logical_name"],
    physical_name=value.get("physical_name"),
    depends_on=tuple(
      parse_runtime_dependency(dependency)
      for dependency in value.get("depends_on", [])
    ),
    lifecycle_artifact=value.get("lifecycle_artifact", False),
  )


def parse_runtime_dependency(value: dict) -> RuntimeDependency:
  return RuntimeDependency(
    id=value["id"],
    template_id=value["template_id"],
    type=DependencyType.from_value(value["type"]),
  )


def read_json(path: Path):
  with open(path, "r", encoding="utf-8") as file:
    return json.load(file)


def build_plan_groups() -> list[dict]:
  return [
    deployers.aws.core.all.AllDeployer().plan(),
    deployers.aws.iot.all.AllDeployer().plan(),
    deployers.aws.hierarchy.all.AllDeployer().plan(),
    deployers.aws.event_actions.all.AllDeployer().plan(),
    deployers.aws.init_values.all.AllDeployer().plan(),
  ]


def action_counts(plan_groups: list[dict]) -> dict[str, int]:
  counts = {
    "DESTROY": 0,
    "DEPLOY": 0,
    "NO_CHANGE": 0,
    "UPDATE": 0,
  }

  for _, _, action in iter_plan_actions(plan_groups):
    counts[action["action"]] += 1

  return counts


def blocked_action_summaries(plan_groups: list[dict]) -> list[str]:
  summaries = []

  for group_name, layer_name, action in iter_plan_actions(plan_groups):
    if not action.get("blocked", False):
      continue

    summaries.append(
      f"{group_name}/{layer_name}: "
      f"{action['action']} {action['resource_type']}/{action['resource']} "
      f"{action.get('blockers', [])}"
    )

  return summaries


def iter_plan_actions(plan_groups: list[dict]):
  for group in plan_groups:
    for layer in group["layers"]:
      for action in layer["actions"]:
        yield group["group"], layer["layer"], action


if __name__ == "__main__":
  unittest.main()
