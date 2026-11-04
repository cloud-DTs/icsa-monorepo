from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from scripts.orchestrator import app


class OrchestratorAppCommandTests(unittest.TestCase):
    def test_fed_prepare_only_runs_local_preparation(self) -> None:
        with (
            patch.object(app, "prepare_federation_hooks") as prepare,
            patch.object(app, "configure_federation_hooks") as configure,
            patch.object(app, "_prompt_yes_no") as prompt,
        ):
            app._handle_command(object(), "fed prepare", object())
        prepare.assert_called_once_with()
        configure.assert_not_called()
        prompt.assert_not_called()

    def test_fed_configure_retries_without_terraform(self) -> None:
        with (
            patch.object(app, "configure_federation_hooks") as configure,
            patch.object(app, "_run_fed_sysml_terraform_safely") as terraform,
        ):
            app._handle_command(object(), "fed configure", object())
        configure.assert_called_once_with()
        terraform.assert_not_called()

    def test_hook_failure_does_not_stop_the_watcher(self) -> None:
        with patch.object(app, "configure_federation_hooks", side_effect=SystemExit(1)):
            app._handle_command(object(), "fed configure", object())

    def test_cancelled_federation_apply_never_configures(self) -> None:
        with (
            patch.object(app, "_run_fed_sysml_terraform_plan_safely", return_value=True),
            patch.object(app, "_prompt_yes_no", return_value=False),
            patch.object(app, "_run_fed_sysml_terraform_apply_saved_plan_safely") as apply,
            patch.object(app, "configure_federation_hooks") as configure,
        ):
            app._handle_command(object(), "fed terraform apply", object())
        apply.assert_not_called()
        configure.assert_not_called()

    def test_continue_digital_twin_manager_target_preserves_case(self) -> None:
        matched, target = app._digital_twin_manager_command_target(
            "continue digital-twin-manager PV",
            app.CONTINUE_DIGITAL_TWIN_MANAGER_ALIASES,
        )

        self.assertTrue(matched)
        self.assertEqual(target, "PV")

    def test_destroy_digital_twin_manager_target_preserves_case(self) -> None:
        matched, target = app._digital_twin_manager_command_target(
            "destroy digital-twin-manager Battery",
            app.DESTROY_DIGITAL_TWIN_MANAGER_ALIASES,
        )

        self.assertTrue(matched)
        self.assertEqual(target, "Battery")

    def test_plan_digital_twin_manager_target_preserves_case(self) -> None:
        matched, target = app._digital_twin_manager_command_target(
            "plan digital-twin-manager PV",
            app.PLAN_DIGITAL_TWIN_MANAGER_ALIASES,
        )

        self.assertTrue(matched)
        self.assertEqual(target, "PV")

    def test_apply_digital_twin_manager_target_preserves_case(self) -> None:
        matched, target = app._digital_twin_manager_command_target(
            "apply digital-twin-manager Battery",
            app.APPLY_DIGITAL_TWIN_MANAGER_ALIASES,
        )

        self.assertTrue(matched)
        self.assertEqual(target, "Battery")

    def test_plan_and_apply_digital_twin_manager_support_action_suffix(self) -> None:
        plan_matched, plan_target = app._digital_twin_manager_command_target(
            "digital-twin-manager plan PV",
            app.PLAN_DIGITAL_TWIN_MANAGER_ALIASES,
        )
        apply_matched, apply_target = app._digital_twin_manager_command_target(
            "digital-twin-manager apply PV",
            app.APPLY_DIGITAL_TWIN_MANAGER_ALIASES,
        )

        self.assertTrue(plan_matched)
        self.assertEqual(plan_target, "PV")
        self.assertTrue(apply_matched)
        self.assertEqual(apply_target, "PV")

    def test_plan_action_suffix_is_not_handled_as_deploy(self) -> None:
        with (
            patch.object(app, "_select_manager_deployment", return_value="PV"),
            patch.object(app, "_run_digital_twin_manager_action_safely", return_value=True) as run_manager,
            patch.object(app, "_run_digital_twin_manager_apply_with_confirmation", return_value=False) as run_apply,
        ):
            app._handle_command(object(), "digital-twin-manager plan PV", object())

        run_manager.assert_called_once_with(ANY, "plan", "PV")
        run_apply.assert_called_once_with(ANY, ANY, "PV")

    def test_digital_twin_manager_action_runner_dispatches_each_action(self) -> None:
        config = object()
        with (
            patch.object(app, "run_digital_twin_manager_deploy_stage") as run_deploy,
            patch.object(app, "run_digital_twin_manager_plan_stage") as run_plan,
            patch.object(app, "run_digital_twin_manager_apply_stage") as run_apply,
        ):
            runners = {
                "deploy": run_deploy,
                "plan": run_plan,
                "apply": run_apply,
            }
            for action, expected_runner in runners.items():
                with self.subTest(action=action):
                    self.assertTrue(app._run_digital_twin_manager_action_safely(config, action, "PV"))
                    expected_runner.assert_called_once_with(config, deployment_name="PV")
                    for runner in runners.values():
                        runner.reset_mock()

    def test_prompt_digital_twin_manager_action_retries_until_valid_action(self) -> None:
        user_input = Mock()
        user_input.get_line.side_effect = [None, "unknown", "PLAN"]

        with patch("builtins.print"):
            action = app._prompt_digital_twin_manager_action(user_input, "sysml-v2")

        self.assertEqual(action, "plan")

    def test_prompt_digital_twin_manager_action_accepts_no(self) -> None:
        user_input = Mock()
        user_input.get_line.return_value = "no"

        with patch("builtins.print"):
            action = app._prompt_digital_twin_manager_action(user_input, "sysml-v1")

        self.assertIsNone(action)

    def test_sysml_command_continues_pipeline_after_converter(self) -> None:
        config = object()
        user_input = object()
        with (
            patch.object(app, "_run_staged_converter_safely", return_value=True) as run_converter,
            patch.object(app, "_continue_pipeline_after_converter") as continue_pipeline,
        ):
            app._handle_command(config, "continue sysml-v1", user_input)

        run_converter.assert_called_once_with(config, "v1", None)
        continue_pipeline.assert_called_once_with(config, user_input, "sysml-v1")

    def test_plan_after_converter_prompts_to_apply_current_deployment(self) -> None:
        config = object()
        user_input = object()
        with (
            patch.object(app, "_prompt_digital_twin_manager_action", return_value="plan"),
            patch.object(app, "read_manager_input_twin_name", return_value="Battery"),
            patch.object(app, "_run_digital_twin_manager_action_safely", return_value=True) as run_manager,
            patch.object(
                app,
                "_run_digital_twin_manager_apply_with_confirmation",
                return_value=False,
            ) as run_apply,
            patch.object(app, "_prompt_yes_no") as prompt_yes_no,
            patch.object(app, "_run_federation_safely") as run_federation,
        ):
            app._continue_pipeline_after_converter(config, user_input, "sysml-v2")

        run_manager.assert_called_once_with(config, "plan", deployment_name="Battery")
        run_apply.assert_called_once_with(config, user_input, "Battery")
        prompt_yes_no.assert_not_called()
        run_federation.assert_not_called()

    def test_plan_after_converter_can_apply_and_continue_with_federation(self) -> None:
        config = object()
        user_input = object()
        with (
            patch.object(app, "_prompt_digital_twin_manager_action", return_value="plan"),
            patch.object(app, "read_manager_input_twin_name", return_value="Battery"),
            patch.object(app, "_run_digital_twin_manager_action_safely", return_value=True) as run_manager,
            patch.object(
                app,
                "_run_digital_twin_manager_apply_with_confirmation",
                return_value=True,
            ) as run_apply,
            patch.object(app, "_prompt_yes_no", return_value=True) as prompt_yes_no,
            patch.object(app, "_run_federation_safely") as run_federation,
        ):
            app._continue_pipeline_after_converter(config, user_input, "sysml-v2")

        run_manager.assert_called_once_with(config, "plan", deployment_name="Battery")
        run_apply.assert_called_once_with(config, user_input, "Battery")
        prompt_yes_no.assert_called_once_with(
            user_input,
            "Run federation workflow after digital twin manager apply? [y/N] ",
        )
        run_federation.assert_called_once_with(config)

    def test_deploy_after_converter_can_continue_with_federation(self) -> None:
        config = object()
        user_input = object()
        with (
            patch.object(app, "_prompt_digital_twin_manager_action", return_value="deploy"),
            patch.object(app, "read_manager_input_twin_name", return_value="Battery"),
            patch.object(app, "_run_digital_twin_manager_action_safely", return_value=True) as run_manager,
            patch.object(app, "_prompt_yes_no", return_value=True) as prompt_yes_no,
            patch.object(app, "_run_federation_safely") as run_federation,
        ):
            app._continue_pipeline_after_converter(config, user_input, "sysml-v2")

        run_manager.assert_called_once_with(config, "deploy", deployment_name="Battery")
        prompt_yes_no.assert_called_once_with(
            user_input,
            "Run federation workflow after digital twin manager deploy? [y/N] ",
        )
        run_federation.assert_called_once_with(config)

    def test_apply_after_converter_can_be_cancelled(self) -> None:
        config = object()
        user_input = object()
        with (
            patch.object(app, "_prompt_digital_twin_manager_action", return_value="apply"),
            patch.object(app, "read_manager_input_twin_name", return_value="Battery"),
            patch.object(
                app,
                "_run_digital_twin_manager_apply_with_confirmation",
                return_value=False,
            ) as run_apply,
            patch.object(app, "_prompt_yes_no") as prompt_yes_no,
        ):
            app._continue_pipeline_after_converter(config, user_input, "sysml-v2")

        run_apply.assert_called_once_with(config, user_input, "Battery")
        prompt_yes_no.assert_not_called()

    def test_apply_confirmation_runs_saved_plan(self) -> None:
        config = object()
        user_input = object()
        with (
            patch.object(app, "_prompt_yes_no", return_value=True) as prompt_yes_no,
            patch.object(app, "_run_digital_twin_manager_action_safely", return_value=True) as run_manager,
        ):
            applied = app._run_digital_twin_manager_apply_with_confirmation(
                config,
                user_input,
                "Battery",
            )

        self.assertTrue(applied)
        prompt_yes_no.assert_called_once_with(
            user_input,
            "Apply the saved digital-twin-manager plan for Battery? [y/N] ",
        )
        run_manager.assert_called_once_with(config, "apply", "Battery")

    def test_apply_confirmation_can_keep_saved_plan_without_applying(self) -> None:
        config = object()
        user_input = object()
        with (
            patch.object(app, "_prompt_yes_no", return_value=False),
            patch.object(app, "_run_digital_twin_manager_action_safely") as run_manager,
        ):
            applied = app._run_digital_twin_manager_apply_with_confirmation(
                config,
                user_input,
                "Battery",
            )

        self.assertFalse(applied)
        run_manager.assert_not_called()

    def test_continue_digital_twin_manager_without_target_matches_menu_mode(self) -> None:
        matched, target = app._digital_twin_manager_command_target(
            "continue digital-twin-manager",
            app.CONTINUE_DIGITAL_TWIN_MANAGER_ALIASES,
        )

        self.assertTrue(matched)
        self.assertIsNone(target)

    def test_digital_twin_target_can_contain_hyphens(self) -> None:
        matched, target = app._digital_twin_manager_command_target(
            "continue digital-twin-manager dtc-y-03",
            app.CONTINUE_DIGITAL_TWIN_MANAGER_ALIASES,
        )

        self.assertTrue(matched)
        self.assertEqual(target, "dtc-y-03")

    def test_continue_sysml_v1_short_command_matches(self) -> None:
        converter, target = app._sysml_profile_command_target("continue sysml-v1")

        self.assertEqual(converter, "v1")
        self.assertIsNone(target)

    def test_continue_sysml_v2_short_command_matches(self) -> None:
        converter, target = app._sysml_profile_command_target("continue sysml-v2")

        self.assertEqual(converter, "v2")
        self.assertIsNone(target)

    def test_continue_sysml_profile_long_command_matches(self) -> None:
        converter, target = app._sysml_profile_command_target("continue digital-twin-profile-sysml-v1")

        self.assertEqual(converter, "v1")
        self.assertIsNone(target)

    def test_continue_sysml_v2_target_is_preserved_for_selection(self) -> None:
        converter, target = app._sysml_profile_command_target("continue sysml-v2 demo.sysml")

        self.assertEqual(converter, "v2")
        self.assertEqual(target, "demo.sysml")

    def test_resolve_staged_file_selection_supports_number_and_name(self) -> None:
        sources = [Path("first.sysml"), Path("Second.sysml")]

        self.assertEqual(app._resolve_staged_file_selection("1", sources), Path("first.sysml"))
        self.assertEqual(app._resolve_staged_file_selection("second.sysml", sources), Path("Second.sysml"))
        self.assertIsNone(app._resolve_staged_file_selection("missing.sysml", sources))

    def test_resolve_manager_deployment_selection_supports_number_and_name(self) -> None:
        deployments = ["Battery", "PV"]

        self.assertEqual(app._resolve_manager_deployment_selection("1", deployments), "Battery")
        self.assertEqual(app._resolve_manager_deployment_selection("pv", deployments), "PV")
        self.assertIsNone(app._resolve_manager_deployment_selection("Unknown", deployments))

    def test_start_simulator_target_preserves_case(self) -> None:
        matched, target = app._simulator_command_target(
            "start simulator PV",
            app.START_SIMULATOR_ALIASES,
        )

        self.assertTrue(matched)
        self.assertEqual(target, "PV")

    def test_stop_simulator_target_preserves_case(self) -> None:
        matched, target = app._simulator_command_target(
            "stop simulator Battery",
            app.STOP_SIMULATOR_ALIASES,
        )

        self.assertTrue(matched)
        self.assertEqual(target, "Battery")

    def test_start_simulator_without_target_matches_menu_mode(self) -> None:
        matched, target = app._simulator_command_target(
            "start simulator",
            app.START_SIMULATOR_ALIASES,
        )

        self.assertTrue(matched)
        self.assertIsNone(target)

    def test_simulator_target_can_contain_hyphens(self) -> None:
        matched, target = app._simulator_command_target(
            "stop simulator dtc-y-03",
            app.STOP_SIMULATOR_ALIASES,
        )

        self.assertTrue(matched)
        self.assertEqual(target, "dtc-y-03")

    def test_start_grafana_matches_without_target(self) -> None:
        matched, target = app._grafana_command_target(
            "start grafana",
            app.START_GRAFANA_ALIASES,
        )

        self.assertTrue(matched)
        self.assertIsNone(target)

    def test_grafana_alias_matches_without_target(self) -> None:
        matched, target = app._grafana_command_target(
            "grafana",
            app.START_GRAFANA_ALIASES,
        )

        self.assertTrue(matched)
        self.assertIsNone(target)

    def test_stop_grafana_matches_without_target(self) -> None:
        matched, target = app._grafana_command_target(
            "stop grafana",
            app.STOP_GRAFANA_ALIASES,
        )

        self.assertTrue(matched)
        self.assertIsNone(target)


if __name__ == "__main__":
    unittest.main()
