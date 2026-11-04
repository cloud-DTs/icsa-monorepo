from __future__ import annotations

import unittest

from src.deployers.aws.core.plan_actions import plan_action


class PlanActionTests(unittest.TestCase):
  def test_plan_action_keeps_explicit_graph_id(self) -> None:
    action = plan_action(
      "dt-dispatcher",
      "lambda_function",
      graph_id="core:l1:dispatcher_lambda:lambda_function:dispatcher",
    )

    self.assertEqual(
      "core:l1:dispatcher_lambda:lambda_function:dispatcher",
      action["graph_id"],
    )

  def test_plan_action_defaults_graph_id_for_legacy_callers(self) -> None:
    action = plan_action("dt-dispatcher", "lambda_function")

    self.assertIsNone(action["graph_id"])


if __name__ == "__main__":
  unittest.main()
