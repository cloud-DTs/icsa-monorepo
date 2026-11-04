from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import StubAwsClient, StubStsClient, install_aws_stubs

install_aws_stubs()

import globals
from deployers.aws.core.persister_iam_role import PersisterIamRoleDeployer
from deployers.aws.core.event_checker_iam_role import EventCheckerIamRoleDeployer
from deployers.aws.core.twinmaker_iam_role import TwinmakerIamRoleDeployer
from deployers.aws.core.hot_reader_iam_role import HotReaderIamRoleDeployer
from deployers.aws.core.hot_cold_mover_iam_role import HotColdMoverIamRoleDeployer
from deployers.aws.core.cold_archive_mover_iam_role import ColdArchiveMoverIamRoleDeployer
from deployers.aws.core.event_feedback_iam_role import EventFeedbackIamRoleDeployer
from deployers.aws.core.grafana_iam_role import GrafanaIamRoleDeployer


# Any managed policy matching this is over-broad for a runtime execution role.
FORBIDDEN_MANAGED_POLICY_PATTERN = re.compile(
  r"(FullAccess(_v2)?|ReadOnlyAccess|AWSIoTDataAccess)$"
)
ALLOWED_MANAGED_POLICY_ARNS = {
  "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
  "arn:aws:iam::aws:policy/service-role/AWSLambdaRole",
}

# service-level wildcard actions (e.g. "dynamodb:*") combined with Resource:"*"
# are the over-broad pattern this fix removes.
WILDCARD_ACTION_PATTERN = re.compile(r"^[a-zA-Z0-9-]+:\*$")

# The one AWS-documented exception left in this fix (grafana_iam_role.py),
# sourced from AWS's own IAM guide for the grafana-iot-twinmaker-app plugin.
ALLOWED_WILDCARD_RESOURCE_ACTIONS = {"iottwinmaker:ListWorkspaces"}


class RecordingIamClient:
  def __init__(self):
    self.create_role_calls = []
    self.attach_role_policy_calls = []
    self.put_role_policy_calls = []
    self.update_assume_role_policy_calls = []

  def create_role(self, **kwargs):
    self.create_role_calls.append(kwargs)
    role_name = kwargs["RoleName"]
    return {"Role": {"Arn": f"arn:aws:iam::123456789012:role/{role_name}"}}

  def get_role(self, RoleName):
    return {
      "Role": {
        "AssumeRolePolicyDocument": {
          "Version": "2012-10-17",
          "Statement": {
            "Effect": "Allow",
            "Principal": {"Service": "grafana.amazonaws.com"},
            "Action": "sts:AssumeRole",
          },
        }
      }
    }

  def update_assume_role_policy(self, **kwargs):
    self.update_assume_role_policy_calls.append(kwargs)

  def attach_role_policy(self, **kwargs):
    self.attach_role_policy_calls.append(kwargs)

  def put_role_policy(self, **kwargs):
    self.put_role_policy_calls.append(kwargs)


def _all_statements(policy_document_json):
  import json

  document = json.loads(policy_document_json)
  return document["Statement"]


def _resources(statement):
  resource = statement["Resource"]
  return resource if isinstance(resource, list) else [resource]


def _actions(statement):
  action = statement["Action"]
  return action if isinstance(action, list) else [action]


DEPLOYER_CLASSES = [
  PersisterIamRoleDeployer,
  EventCheckerIamRoleDeployer,
  TwinmakerIamRoleDeployer,
  HotReaderIamRoleDeployer,
  HotColdMoverIamRoleDeployer,
  ColdArchiveMoverIamRoleDeployer,
  EventFeedbackIamRoleDeployer,
  GrafanaIamRoleDeployer,
]


class IamRoleLeastPrivilegeTests(unittest.TestCase):
  def setUp(self) -> None:
    self.original_globals = {
      "config": globals.config,
      "config_events": getattr(globals, "config_events", []),
      "aws_iam_client": globals.aws_iam_client,
      "aws_lambda_client": globals.aws_lambda_client,
      "aws_dynamodb_client": globals.aws_dynamodb_client,
      "aws_s3_client": globals.aws_s3_client,
      "aws_twinmaker_client": globals.aws_twinmaker_client,
      "aws_sf_client": globals.aws_sf_client,
      "aws_iot_client": globals.aws_iot_client,
      "aws_sts_client": globals.aws_sts_client,
    }

    globals.config = {
      "digital_twin_name": "dtc-y-01",
      "hot_storage_size_in_days": 30,
      "cold_storage_size_in_days": 60,
    }
    globals.config_events = [
      {
        "condition": "entity.component.property > INTEGER(1)",
        "action": {
          "type": "lambda",
          "functionName": "high-temperature-callback",
          "external": False,
          "feedback": {
            "type": "mqtt",
            "topic": "dtc-y-01-custom-topic",
            "payload": "action-result",
          },
        },
      },
      {
        "condition": "entity.component.property2 > INTEGER(2)",
        "action": {
          "type": "lambda",
          "functionName": "another-callback",
          "external": True,
          "feedback": {
            "type": "mqtt",
            "payload": "action-result",
            "iotDeviceId": "battery-sensor",
          },
        },
      },
      {
        "condition": "entity.component.property3 > INTEGER(3)",
        "action": {
          "type": "lambda",
          "functionName": "no-feedback-callback",
          "external": False,
        },
      },
    ]

    globals.aws_iam_client = RecordingIamClient()
    globals.aws_lambda_client = StubAwsClient()
    globals.aws_dynamodb_client = StubAwsClient()
    globals.aws_s3_client = StubAwsClient()
    globals.aws_twinmaker_client = StubAwsClient()
    globals.aws_sf_client = StubAwsClient()
    globals.aws_iot_client = StubAwsClient()
    globals.aws_sts_client = StubStsClient()

    sleep_patcher = patch("time.sleep")
    sleep_patcher.start()
    self.addCleanup(sleep_patcher.stop)

  def tearDown(self) -> None:
    for name, value in self.original_globals.items():
      setattr(globals, name, value)

  def test_no_over_broad_managed_policies_attached(self) -> None:
    for deployer_class in DEPLOYER_CLASSES:
      with self.subTest(deployer=deployer_class.__name__):
        globals.aws_iam_client = RecordingIamClient()
        deployer_class().deploy()

        for call in globals.aws_iam_client.attach_role_policy_calls:
          policy_arn = call["PolicyArn"]
          self.assertNotRegex(
            policy_arn,
            FORBIDDEN_MANAGED_POLICY_PATTERN,
            f"{deployer_class.__name__} attached over-broad managed policy {policy_arn}",
          )
          self.assertIn(
            policy_arn,
            ALLOWED_MANAGED_POLICY_ARNS,
            f"{deployer_class.__name__} attached unexpected managed policy {policy_arn}",
          )

  def test_no_stray_wildcard_resource_statements(self) -> None:
    for deployer_class in DEPLOYER_CLASSES:
      with self.subTest(deployer=deployer_class.__name__):
        globals.aws_iam_client = RecordingIamClient()
        deployer_class().deploy()

        for call in globals.aws_iam_client.put_role_policy_calls:
          for statement in _all_statements(call["PolicyDocument"]):
            if "*" not in _resources(statement):
              continue

            for action in _actions(statement):
              is_wildcard_action = WILDCARD_ACTION_PATTERN.match(action) is not None
              is_documented_exception = action in ALLOWED_WILDCARD_RESOURCE_ACTIONS

              self.assertFalse(
                is_wildcard_action,
                f"{deployer_class.__name__} grants wildcard action {action} on Resource:\"*\"",
              )

              if not is_documented_exception:
                self.fail(
                  f"{deployer_class.__name__} grants undocumented action {action} on "
                  f"Resource:\"*\" (only {ALLOWED_WILDCARD_RESOURCE_ACTIONS} are allowed)"
                )

  def test_twinmaker_bucket_location_permission_is_scoped_to_its_workspace_bucket(self) -> None:
    TwinmakerIamRoleDeployer().deploy()

    location_permissions = [
      (call["RoleName"], resource)
      for call in globals.aws_iam_client.put_role_policy_calls
      for statement in _all_statements(call["PolicyDocument"])
      if statement["Effect"] == "Allow" and "s3:GetBucketLocation" in _actions(statement)
      for resource in _resources(statement)
    ]

    self.assertEqual(
      [("dtc-y-01-twinmaker", "arn:aws:s3:::dtc-y-01-twinmaker")],
      location_permissions,
    )

  def test_service_trust_policies_are_bound_to_the_account(self) -> None:
    import json

    account_id = globals.aws_sts_client.get_caller_identity()["Account"]

    for deployer_class in DEPLOYER_CLASSES:
      with self.subTest(deployer=deployer_class.__name__):
        globals.aws_iam_client = RecordingIamClient()
        deployer_class().deploy()

        self.assertEqual(len(globals.aws_iam_client.create_role_calls), 1)
        trust_policy = json.loads(
          globals.aws_iam_client.create_role_calls[0]["AssumeRolePolicyDocument"]
        )

        for statement in trust_policy["Statement"]:
          self.assertIn("Service", statement["Principal"])
          self.assertEqual(
            statement["Condition"],
            {"StringEquals": {"aws:SourceAccount": account_id}},
            f"{deployer_class.__name__} trust policy is not bound to the account",
          )

  def test_event_checker_has_no_federation_support(self) -> None:
    EventCheckerIamRoleDeployer().deploy()

    for call in globals.aws_iam_client.put_role_policy_calls:
      for statement in _all_statements(call["PolicyDocument"]):
        actions = _actions(statement)
        self.assertNotIn("ssm:GetParameter", actions)

        for action in ("states:StartExecution", "lambda:InvokeFunction"):
          if action not in actions:
            continue

          for resource in _resources(statement):
            self.assertNotEqual(resource, "*")
            self.assertTrue(
              resource.startswith("arn:aws:states:")
              or resource.startswith("arn:aws:lambda:"),
              f"unexpected resource {resource} for {action}",
            )
            self.assertIn(
              "dtc-y-01",
              resource,
              f"{action} resource {resource} is not scoped to this twin",
            )

  def test_event_feedback_topics_are_enumerated_from_config_events(self) -> None:
    EventFeedbackIamRoleDeployer().deploy()

    self.assertEqual(1, len(globals.aws_iam_client.put_role_policy_calls))
    statements = _all_statements(
      globals.aws_iam_client.put_role_policy_calls[0]["PolicyDocument"]
    )
    self.assertEqual(1, len(statements))
    self.assertEqual(["iot:Publish"], _actions(statements[0]))
    self.assertEqual(
      [
        "arn:aws:iot:eu-west-1:123456789012:topic/dtc-y-01-battery-sensor",
        "arn:aws:iot:eu-west-1:123456789012:topic/dtc-y-01-custom-topic",
      ],
      sorted(_resources(statements[0])),
    )

  def test_event_feedback_skips_inline_policy_when_no_mqtt_feedback(self) -> None:
    globals.config_events = [
      {
        "condition": "entity.component.property > INTEGER(1)",
        "action": {
          "type": "lambda",
          "functionName": "no-feedback-callback",
          "external": False,
        },
      }
    ]

    EventFeedbackIamRoleDeployer().deploy()

    self.assertEqual([], globals.aws_iam_client.put_role_policy_calls)


if __name__ == "__main__":
  unittest.main()
