from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import StubStsClient, install_aws_stubs

install_aws_stubs()

import deployment_state
import globals
from deployers.aws.core.event_checker_lambda_function import (
  EventCheckerLambdaFunctionDeployer,
)
from tests.test_managed_lambda_regressions import ManagedLambdaClient, ManagedIamClient


class EventCheckerLambdaPlanTests(unittest.TestCase):
  def setUp(self) -> None:
    self.config = {
      "digital_twin_name": "dtc-y-01",
      "hot_storage_size_in_days": 30,
      "cold_storage_size_in_days": 30,
    }
    self.previous_events = [
      {
        "condition": "entity.component.temperature > 10",
        "action": {
          "type": "lambda",
          "functionName": "alertAction",
          "external": True,
        },
      }
    ]
    self.desired_events = [
      {
        "condition": "entity-renamed.component.temperature > 10",
        "action": {
          "type": "lambda",
          "functionName": "alertAction",
          "external": True,
        },
      }
    ]

    for target, name, value in (
      (globals, "config", dict(self.config)),
      (globals, "config_iot_devices", []),
      (globals, "config_events", self.previous_events),
      (globals, "aws_lambda_client", ManagedLambdaClient()),
      (globals, "aws_iam_client", ManagedIamClient()),
      (globals, "aws_sts_client", StubStsClient()),
      (deployment_state, "last_applied_config", dict(self.config)),
      (deployment_state, "last_applied_config_iot_devices", []),
      (deployment_state, "last_applied_config_events", self.previous_events),
      (deployment_state, "last_applied_state_metadata", {"awsRegion": "eu-west-1"}),
    ):
      patcher = patch.object(target, name, value, create=True)
      patcher.start()
      self.addCleanup(patcher.stop)
    EventCheckerLambdaFunctionDeployer().deploy()
    globals.config_events = self.desired_events

  def test_config_events_change_updates_event_checker_lambda(self) -> None:
    actions = EventCheckerLambdaFunctionDeployer().plan()

    self.assertEqual(
      ["UPDATE"],
      [action["action"] for action in actions],
    )
    self.assertEqual(
      ["dtc-y-01-event-checker"],
      [action["resource"] for action in actions],
    )

  def test_matching_config_events_are_no_change(self) -> None:
    globals.aws_lambda_client = ManagedLambdaClient()
    EventCheckerLambdaFunctionDeployer().deploy()
    deployment_state.last_applied_config_events = self.desired_events

    actions = EventCheckerLambdaFunctionDeployer().plan()

    self.assertEqual(1, len(actions))
    self.assertEqual("NO_CHANGE", actions[0]["action"])
    self.assertEqual("dtc-y-01-event-checker", actions[0]["resource"])

  def test_iot_device_change_without_config_events_change_is_no_change(self) -> None:
    globals.aws_lambda_client = ManagedLambdaClient()
    EventCheckerLambdaFunctionDeployer().deploy()
    deployment_state.last_applied_config_events = self.desired_events
    deployment_state.last_applied_config_iot_devices = []
    globals.config_iot_devices = [{"id": "new-device", "properties": []}]

    actions = EventCheckerLambdaFunctionDeployer().plan()

    self.assertEqual(1, len(actions))
    self.assertEqual("NO_CHANGE", actions[0]["action"])
    self.assertEqual("dtc-y-01-event-checker", actions[0]["resource"])


if __name__ == "__main__":
  unittest.main()
