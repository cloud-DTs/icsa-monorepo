import copy
import os
from unittest.mock import patch

from tests.test_managed_lambda_regressions import ManagedLambdaFixture

import deployment_state
import globals
from botocore.exceptions import ClientError
from deployers.aws.all import AllDeployer
from deployers.aws.core.hot_cold_mover_lambda_function import HotColdMoverLambdaFunctionDeployer
from deployers.aws.event_actions.lambda_actions import LambdaActionsDeployer


class LambdaUpdateSafetyTests(ManagedLambdaFixture):
  def internal_event_plan(self):
    globals.config_events = [copy.deepcopy(self.event)]
    deployment_state.last_applied_config_events = copy.deepcopy(globals.config_events)
    deployer = LambdaActionsDeployer()
    deployer.deploy()
    globals.config_events[0]["condition"] = "root.sensor.temperature > DOUBLE(20)"
    actions = deployer.plan()
    return self.plan_for_group("event_actions", "event_actions", actions)

  def test_changed_internal_event_condition_can_apply_its_planned_replacement(self):
    plan = self.internal_event_plan()
    self.assertEqual(["DESTROY", "DEPLOY"], [a["action"] for a in plan[0]["layers"][0]["actions"]])
    with patch("deployment_state.mark_plan_action_processed"):
      AllDeployer().apply(plan)
    self.assertIn("dt-alert-action", self.lambda_client.functions)
    deployment_state.last_applied_config_events = copy.deepcopy(globals.config_events)
    self.assertEqual("NO_CHANGE", LambdaActionsDeployer().plan()[-1]["action"])

  def test_replacement_rejects_aws_change_before_deleting_existing_function(self):
    plan = self.internal_event_plan()
    self.lambda_client.functions["dt-alert-action"]["RevisionId"] = "changed-after-plan"
    self.assert_rejected_before_any_group(plan)
    self.assertEqual([], self.lambda_client.delete_requests)

  def test_replacement_rejects_blocked_destroy_before_any_group_mutation(self):
    plan = self.internal_event_plan()
    plan[0]["layers"][0]["actions"][0]["blocked"] = True
    self.assert_rejected_before_any_group(plan)

  def test_new_internal_action_cannot_overwrite_an_existing_unmanaged_function(self):
    globals.config_events = [copy.deepcopy(self.event)]
    LambdaActionsDeployer().deploy()
    plan = self.plan_for_group("event_actions", "event_actions", LambdaActionsDeployer().plan())
    self.assert_rejected_before_any_group(plan)

  def test_embedded_event_config_change_after_plan_rejects_apply(self):
    from deployers.aws.core.event_checker_lambda_function import EventCheckerLambdaFunctionDeployer
    deployer, _ = self.deploy_core(EventCheckerLambdaFunctionDeployer)
    plan = self.plan_for_group("core", "core_l2", deployer.plan())
    globals.config_events.append(copy.deepcopy(self.event))
    self.assert_rejected_before_any_group(plan)

  def test_sdk_revision_guard_rejects_writer_after_final_preflight_read(self):
    deployer, name = self.deploy_core(HotColdMoverLambdaFunctionDeployer)
    self.change_source(self.sources["hot-to-cold-mover"])
    action = self.single_action(deployer.plan(), "UPDATE")
    original_update = self.lambda_client.update_function_code

    def concurrent_update(**request):
      self.lambda_client.functions[name]["RevisionId"] = "concurrent-writer"
      return original_update(**request)

    with patch.object(self.lambda_client, "update_function_code", side_effect=concurrent_update):
      with self.assertRaises(ClientError):
        deployer.apply(action, name)
    self.assertEqual([], self.lambda_client.code_updates)

  def test_processor_update_is_applied_and_recorded_in_forward_phase(self):
    from deployers.aws.iot.all import AllDeployer as IotAllDeployer
    from deployers.aws.iot.l2 import L2Deployer
    from deployers.aws.iot.processor_lambda_function import ProcessorLambdaFunctionDeployer
    deployer = ProcessorLambdaFunctionDeployer()
    deployer.deploy(self.device)
    self.change_source(self.processor_source)
    action = self.single_action(deployer.plan(self.device, self.device), "UPDATE")
    plan = self.plan_for_group("iot", "iot_l2", [action])
    with patch.dict(os.environ, {deployment_state.STATE_DIR_ENV: str(self.project / "state")}), patch.object(
      IotAllDeployer, "LAYERS", [("iot_l2", L2Deployer)],
    ):
      deployment_state.save_plan(plan)
      AllDeployer().apply(plan)
      saved_action = deployment_state.load_plan()[0]["layers"][0]["actions"][0]
      self.assertTrue(saved_action["processed"])
    self.assertEqual(1, len(self.lambda_client.code_updates))

  def test_changed_core_resource_name_is_rejected_before_any_group(self):
    deployer, _ = self.deploy_core(HotColdMoverLambdaFunctionDeployer)
    actions = deployer.plan()
    actions[0]["resource"] = "dt-a-different-function"
    self.assert_rejected_before_any_group(self.plan_for_group("core", "core_l3_hot", actions))

  def test_configuration_update_revision_cannot_adopt_a_concurrent_writer(self):
    deployer, name = self.deploy_core(HotColdMoverLambdaFunctionDeployer)
    globals.config["hot_storage_size_in_days"] = 31
    action = self.single_action(deployer.plan(), "UPDATE")
    original_waiter = self.lambda_client.get_waiter

    def waiter_with_concurrent_writer(waiter_name):
      waiter = original_waiter(waiter_name)
      original_wait = waiter.wait

      def finish_then_change(**request):
        original_wait(**request)
        self.lambda_client.functions[name]["RevisionId"] = "concurrent-writer"
        self.lambda_client.functions[name]["Layers"] = [{"Arn": "a-new-layer"}]

      waiter.wait = finish_then_change
      return waiter

    with patch.object(self.lambda_client, "get_waiter", side_effect=waiter_with_concurrent_writer):
      with self.assertRaises((ValueError, RuntimeError, ClientError)):
        deployer.apply(action, name)
    self.assertEqual([], self.lambda_client.code_updates)
