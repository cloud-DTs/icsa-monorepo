from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.orchestrator import pipeline as orchestrator_pipeline
from scripts.orchestrator import staging


class OrchestratorStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pipeline_root = Path(self.temp_dir.name) / "pipeline"
        self.manager_input = self.pipeline_root / "digital-twin-manager" / "input"
        self.manager_output = self.pipeline_root / "digital-twin-manager" / "output"
        self.manager_deployments = self.pipeline_root / "digital-twin-manager" / "deployments"
        self.federation_input = self.pipeline_root / "fed-sysml" / "input"
        self.federation_output = self.pipeline_root / "fed-sysml" / "output"
        self.profile_v1_input = self.pipeline_root / "digital-twin-profile-sysml-v1" / "input"
        self.profile_v1_output = self.pipeline_root / "digital-twin-profile-sysml-v1" / "output"
        self.profile_v2_input = self.pipeline_root / "digital-twin-profile-sysml-v2" / "input"
        self.profile_v2_output = self.pipeline_root / "digital-twin-profile-sysml-v2" / "output"
        self.grafana_dir = self.pipeline_root / "grafana"
        self.grafana_state = self.grafana_dir / "grafana.json"

        for path in (
            self.manager_input,
            self.manager_output,
            self.manager_deployments,
            self.federation_input / "strategyInputs",
            self.federation_output,
            self.profile_v1_input,
            self.profile_v1_output,
            self.profile_v2_input,
            self.profile_v2_output,
        ):
            path.mkdir(parents=True, exist_ok=True)

        self.original_paths = {
            "PIPELINE_ROOT": staging.PIPELINE_ROOT,
            "MANAGER_INPUT_DIR": staging.MANAGER_INPUT_DIR,
            "MANAGER_OUTPUT_DIR": staging.MANAGER_OUTPUT_DIR,
            "MANAGER_DEPLOYMENTS_DIR": staging.MANAGER_DEPLOYMENTS_DIR,
            "FEDERATION_INPUT_DIR": staging.FEDERATION_INPUT_DIR,
            "FEDERATION_OUTPUT_DIR": staging.FEDERATION_OUTPUT_DIR,
            "PROFILE_INPUT_DIRS": staging.PROFILE_INPUT_DIRS,
            "PROFILE_OUTPUT_DIRS": staging.PROFILE_OUTPUT_DIRS,
            "GRAFANA_DIR": staging.GRAFANA_DIR,
            "GRAFANA_STATE_PATH": staging.GRAFANA_STATE_PATH,
        }
        staging.PIPELINE_ROOT = self.pipeline_root
        staging.MANAGER_INPUT_DIR = self.manager_input
        staging.MANAGER_OUTPUT_DIR = self.manager_output
        staging.MANAGER_DEPLOYMENTS_DIR = self.manager_deployments
        staging.FEDERATION_INPUT_DIR = self.federation_input
        staging.FEDERATION_OUTPUT_DIR = self.federation_output
        staging.PROFILE_INPUT_DIRS = {
            "v1": self.profile_v1_input,
            "v2": self.profile_v2_input,
        }
        staging.PROFILE_OUTPUT_DIRS = {
            "v1": self.profile_v1_output,
            "v2": self.profile_v2_output,
        }
        staging.GRAFANA_DIR = self.grafana_dir
        staging.GRAFANA_STATE_PATH = self.grafana_state

    def tearDown(self) -> None:
        for name, value in self.original_paths.items():
            setattr(staging, name, value)
        self.temp_dir.cleanup()

    def write_json(self, path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def write_sysml_v1_export(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '<xmi:XMI xmlns:xmi="http://www.omg.org/XMI"><elements>'
            '<element><properties stereotype="Twin" /></element>'
            '</elements></xmi:XMI>',
            encoding="utf-8",
        )

    def write_fedtwin(self, strategy_refs: list[str]) -> Path:
        path = self.federation_input / "fedtwin.json"
        self.write_json(
            path,
            {
                "fedTwins": [
                    {
                        "name": "MicroGrid",
                        "newStrategies": [
                            {
                                "name": "ConsumptionStrategy",
                                "strategies": strategy_refs,
                            }
                        ],
                    }
                ]
            },
        )
        return path

    def write_broker_config(self) -> None:
        self.write_json(self.federation_input / "brokerConfig.json", {"brokers": {}})

    def write_manager_config_set(self, directory: Path, twin_name: str) -> None:
        self.write_json(directory / "config.json", {"digital_twin_name": twin_name})
        self.write_json(directory / "config_hierarchy.json", [])
        self.write_json(directory / "config_iot_devices.json", [])
        self.write_json(directory / "config_events.json", [])

    def write_manager_redeployment_state(self, output_dir: Path, twin_name: str, *, include_plan: bool) -> Path:
        state_dir = output_dir / staging.MANAGER_STATE_DIR_NAME
        self.write_json(
            state_dir / staging.MANAGER_STATE_METADATA_FILE_NAME,
            {"digitalTwinName": twin_name, "stateVersion": 1},
        )
        self.write_manager_config_set(state_dir / staging.MANAGER_STATE_CONFIG_DIR_NAME, twin_name)
        if include_plan:
            self.write_json(
                state_dir / staging.MANAGER_STATE_PLAN_FILE_NAME,
                [{"group": "core", "layers": []}],
            )
        return state_dir

    def test_required_twins_accepts_one_twin_with_multiple_strategies(self) -> None:
        fedtwin = self.write_fedtwin(["dtc-y-03.stopCharging", "dtc-y-03.stopChargingP14"])

        self.assertEqual(staging.required_twins_from_fedtwin(fedtwin), ["dtc-y-03"])

    def test_required_twins_deduplicates_two_twin_references(self) -> None:
        fedtwin = self.write_fedtwin(["PV.production", "Battery.status", "PV.production"])

        self.assertEqual(staging.required_twins_from_fedtwin(fedtwin), ["PV", "Battery"])

    def test_required_twins_rejects_invalid_strategy_reference(self) -> None:
        fedtwin = self.write_fedtwin(["PV"])

        with self.assertRaises(SystemExit):
            staging.required_twins_from_fedtwin(fedtwin)

    def test_new_v2_export_preserves_models_and_replaces_only_run_input(self) -> None:
        model = self.profile_v2_input / "MGridICSA.sysml"
        other_model = self.profile_v2_input / "dtcWeather.sysml"
        model.write_bytes(b"package MGridICSA {} // local edits\r\n")
        other_model.write_bytes(b"package Weather {}\r\n")
        source = self.pipeline_root / "MGridICSA.sysml"
        source.write_bytes(b"package NewExport {}\n")
        run_input = self.profile_v2_input.parent / "run-input"
        run_input.mkdir()

        for clean_stage in (True, False):
            with self.subTest(clean_stage=clean_stage):
                (run_input / "previous.sysml").write_text("package Previous {}", encoding="utf-8")
                stale_output = self.profile_v2_output / "stale.txt"
                stale_output.write_text("previous output", encoding="utf-8")

                result = staging.stage_converter_input("v2", source, clean_stage=clean_stage)

                self.assertEqual(model.read_bytes(), b"package MGridICSA {} // local edits\r\n")
                self.assertEqual(other_model.read_bytes(), b"package Weather {}\r\n")
                container_input, used_files, input_host_dir = result
                self.assertIsNone(container_input)
                self.assertEqual(used_files, [source])
                self.assertEqual(input_host_dir, run_input)
                self.assertEqual(sorted(path.name for path in run_input.iterdir()), [source.name])
                self.assertEqual((run_input / source.name).read_bytes(), source.read_bytes())
                self.assertEqual(stale_output.exists(), not clean_stage)

    def test_new_v2_export_can_use_a_model_from_input(self) -> None:
        source = self.profile_v2_input / "MGridICSA.sysml"
        source.write_text("package MGridICSA {}", encoding="utf-8")

        _, used_files, input_host_dir = staging.stage_converter_input("v2", source, clean_stage=True)

        self.assertEqual(source.read_text(encoding="utf-8"), "package MGridICSA {}")
        self.assertEqual(used_files, [source])
        self.assertEqual((input_host_dir / source.name).read_bytes(), source.read_bytes())

    def test_new_v2_export_directory_stages_all_its_models(self) -> None:
        source = self.pipeline_root / "exports"
        source.mkdir()
        first = source / "first.sysml"
        second = source / "second.sysml"
        first.write_text("package First {}", encoding="utf-8")
        second.write_text("package Second {}", encoding="utf-8")
        existing = self.profile_v2_input / "existing.sysml"
        existing.write_text("package Existing {}", encoding="utf-8")

        _, used_files, input_host_dir = staging.stage_converter_input("v2", source, clean_stage=True)

        self.assertEqual(used_files, [first, second])
        self.assertEqual(sorted(path.name for path in input_host_dir.iterdir()), [first.name, second.name])
        self.assertEqual(existing.read_text(encoding="utf-8"), "package Existing {}")

    def test_invalid_new_v2_export_preserves_existing_files(self) -> None:
        model = self.profile_v2_input / "MGridICSA.sysml"
        model.write_text("package MGridICSA {}", encoding="utf-8")
        previous_output = self.profile_v2_output / "previous.txt"
        previous_output.write_text("previous output", encoding="utf-8")
        source = self.pipeline_root / "export.xml"
        self.write_sysml_v1_export(source)

        with self.assertRaises(SystemExit):
            staging.stage_converter_input("v2", source, clean_stage=True)

        self.assertEqual(model.read_text(encoding="utf-8"), "package MGridICSA {}")
        self.assertEqual(previous_output.read_text(encoding="utf-8"), "previous output")

    def test_new_v1_export_keeps_its_converter_input_contract(self) -> None:
        source = self.pipeline_root / "export.xml"
        self.write_sysml_v1_export(source)

        container_input, used_files, input_host_dir = staging.stage_converter_input("v1", source, clean_stage=True)

        self.assertEqual(container_input, "/pipeline/input/export.xml")
        self.assertEqual(used_files, [source])
        self.assertIsNone(input_host_dir)
        self.assertEqual((self.profile_v1_input / source.name).read_bytes(), source.read_bytes())

    def test_new_v2_export_rejects_run_input_as_its_source_without_deleting_it(self) -> None:
        run_input = self.profile_v2_input.parent / "run-input"
        run_input.mkdir()
        source = run_input / "export.sysml"
        source.write_text("package Export {}", encoding="utf-8")

        with self.assertRaises(SystemExit):
            staging.stage_converter_input("v2", source, clean_stage=True)

        self.assertEqual(source.read_text(encoding="utf-8"), "package Export {}")

    def test_new_v2_export_mounts_run_input_for_the_converter(self) -> None:
        source = self.pipeline_root / "export.sysml"
        source.write_text("package Export {}", encoding="utf-8")
        compose_file = self.pipeline_root / "docker-compose.yaml"
        compose_file.write_text("services: {}", encoding="utf-8")
        config = SimpleNamespace(
            compose_file=compose_file, compose_profiles=("pipeline",),
            run_federation_workflow=False, deploy_to_aws=False, clean_stage=True,
            digital_twin_name="dtwin", path_maps=(), build_images=False, show_container_logs=False,
        )

        with (
            patch.object(orchestrator_pipeline, "run_converter", side_effect=SystemExit(0)) as run,
            self.assertRaises(SystemExit),
        ):
            orchestrator_pipeline.run_pipeline(config, source=source, converter="v2")

        run_input = self.profile_v2_input.parent / "run-input"
        self.assertEqual(run.call_args.kwargs.get("input_host_dir"), run_input)
        self.assertEqual((run_input / source.name).read_bytes(), source.read_bytes())

    def test_select_staged_converter_input_v1_accepts_one_xml(self) -> None:
        source = self.profile_v1_input / "model.xml"
        self.write_sysml_v1_export(source)
        (self.profile_v1_output / "stale.txt").write_text("old", encoding="utf-8")

        container_input, used_files, input_host_dir = staging.select_staged_converter_input("v1", clean_output=True)

        self.assertEqual(container_input, "/pipeline/input/model.xml")
        self.assertEqual(used_files, [source])
        self.assertIsNone(input_host_dir)
        self.assertFalse((self.profile_v1_output / "stale.txt").exists())

    def test_select_staged_converter_input_v1_rejects_multiple_xml_xmi(self) -> None:
        self.write_sysml_v1_export(self.profile_v1_input / "model.xml")
        self.write_sysml_v1_export(self.profile_v1_input / "model.xmi")

        with self.assertRaises(SystemExit):
            staging.select_staged_converter_input("v1", clean_output=True)

    def test_select_staged_converter_input_v2_accepts_sysml(self) -> None:
        source = self.profile_v2_input / "model.sysml"
        source.write_text("package Demo {}", encoding="utf-8")

        container_input, used_files, input_host_dir = staging.select_staged_converter_input("v2", clean_output=True)

        self.assertIsNone(container_input)
        self.assertEqual(used_files, [source])
        self.assertIsNone(input_host_dir)

    def test_select_staged_converter_input_v2_can_prepare_selected_run_input(self) -> None:
        first = self.profile_v2_input / "first.sysml"
        second = self.profile_v2_input / "second.sysml"
        first.write_text("package First {}", encoding="utf-8")
        second.write_text("package Second {}", encoding="utf-8")

        container_input, used_files, input_host_dir = staging.select_staged_converter_input(
            "v2",
            clean_output=True,
            selected_input=second,
        )

        self.assertIsNone(container_input)
        self.assertEqual(used_files, [second])
        self.assertEqual(input_host_dir, self.profile_v2_input.parent / "run-input")
        self.assertTrue((input_host_dir / "second.sysml").is_file())
        self.assertFalse((input_host_dir / "first.sysml").exists())

    def test_select_staged_converter_input_v2_rejects_xml(self) -> None:
        self.write_sysml_v1_export(self.profile_v2_input / "model.xml")

        with self.assertRaises(SystemExit):
            staging.select_staged_converter_input("v2", clean_output=True)

    def test_save_manager_deployment_input_copies_current_manager_input(self) -> None:
        self.write_manager_config_set(self.manager_input, "PV")
        self.write_json(self.manager_input / "config_credentials.json", {"aws_region": "eu-central-1"})

        saved_input = staging.save_manager_deployment_input()

        self.assertEqual(saved_input, self.manager_deployments / "PV" / "input")
        self.assertTrue((saved_input / "config.json").is_file())
        self.assertTrue((saved_input / "config_credentials.json").is_file())
        self.assertEqual(staging.list_manager_deployments(), ["PV"])

    def test_stage_manager_input_preserves_credentials_and_providers_when_cleaning(self) -> None:
        credentials = b'{"aws_region": "eu-central-1"}'
        providers = b'{"layer_1_provider": "aws"}'
        (self.manager_input / "config_credentials.json").write_bytes(credentials)
        (self.manager_input / "config_providers.json").write_bytes(providers)
        (self.manager_input / "stale.json").write_text("{}", encoding="utf-8")
        converter_output = self.pipeline_root / "converter-output"
        self.write_manager_config_set(converter_output, "PV")

        orchestrator_pipeline.stage_digital_twin_manager_input(
            SimpleNamespace(aws_credentials_file=None, clean_stage=True, show_configs=False),
            converter_output,
        )

        self.assertEqual((self.manager_input / "config_credentials.json").read_bytes(), credentials)
        self.assertEqual((self.manager_input / "config_providers.json").read_bytes(), providers)
        self.assertFalse((self.manager_input / "stale.json").exists())
        saved_input = self.manager_deployments / "PV" / "input"
        self.assertEqual((saved_input / "config_providers.json").read_bytes(), providers)

    def test_save_manager_deployment_output_preserves_saved_input(self) -> None:
        self.write_manager_config_set(self.manager_input, "PV")
        staging.save_manager_deployment_input()
        self.write_json(self.manager_output / "PV_federation_input.json", {"name": "PV"})
        self.write_json(self.manager_output / "Battery_federation_input.json", {"name": "Battery"})
        auth_dir = self.manager_output / "iot_devices_auth"
        auth_dir.mkdir()
        (auth_dir / "device.json").write_text("{}", encoding="utf-8")

        saved_artifact = staging.save_manager_deployment_output()

        self.assertEqual(saved_artifact, self.manager_deployments / "PV" / "output" / "PV_federation_input.json")
        self.assertTrue(saved_artifact.is_file())
        self.assertTrue((self.manager_deployments / "PV" / "input" / "config.json").is_file())
        self.assertTrue((self.manager_deployments / "PV" / "output" / "iot_devices_auth" / "device.json").is_file())
        self.assertFalse((self.manager_deployments / "PV" / "output" / "Battery_federation_input.json").exists())

    def test_save_manager_deployment_input_preserves_existing_output(self) -> None:
        self.write_manager_config_set(self.manager_input, "PV")
        self.write_json(self.manager_deployments / "PV" / "output" / "PV_federation_input.json", {"name": "PV"})

        staging.save_manager_deployment_input()

        self.assertTrue((self.manager_deployments / "PV" / "output" / "PV_federation_input.json").is_file())

    def test_restore_manager_deployment_input_cleans_and_restores_selected_input(self) -> None:
        self.write_manager_config_set(self.manager_deployments / "PV" / "input", "PV")
        self.write_json(self.manager_input / "stale.json", {"stale": True})

        restored_input = staging.restore_manager_deployment_input("pv")

        self.assertEqual(restored_input, self.manager_input)
        self.assertTrue((self.manager_input / "config.json").is_file())
        self.assertFalse((self.manager_input / "stale.json").exists())

    def test_restore_manager_deployment_output_restores_state_and_saved_plan(self) -> None:
        deployment_dir = self.manager_deployments / "PV"
        self.write_manager_config_set(deployment_dir / "input", "PV")
        self.write_json(deployment_dir / "output" / "PV_federation_input.json", {"name": "PV"})
        self.write_manager_redeployment_state(deployment_dir / "output", "PV", include_plan=True)
        self.write_json(self.manager_output / "stale.json", {"stale": True})

        restored_output = staging.restore_manager_deployment_output("pv", require_plan=True)

        self.assertEqual(restored_output, self.manager_output)
        self.assertTrue((self.manager_output / "PV_federation_input.json").is_file())
        self.assertTrue(
            (
                self.manager_output
                / staging.MANAGER_STATE_DIR_NAME
                / staging.MANAGER_STATE_PLAN_FILE_NAME
            ).is_file()
        )
        self.assertFalse((self.manager_output / "stale.json").exists())

    def test_restore_manager_deployment_output_requires_plan_for_apply(self) -> None:
        deployment_dir = self.manager_deployments / "PV"
        self.write_manager_config_set(deployment_dir / "input", "PV")
        self.write_manager_redeployment_state(deployment_dir / "output", "PV", include_plan=False)

        with self.assertRaises(SystemExit):
            staging.restore_manager_deployment_output("PV", require_plan=True)

    def test_restore_manager_deployment_output_rejects_empty_plan_for_apply(self) -> None:
        deployment_dir = self.manager_deployments / "PV"
        self.write_manager_config_set(deployment_dir / "input", "PV")
        state_dir = self.write_manager_redeployment_state(deployment_dir / "output", "PV", include_plan=True)
        self.write_json(state_dir / staging.MANAGER_STATE_PLAN_FILE_NAME, [])

        with self.assertRaises(SystemExit):
            staging.restore_manager_deployment_output("PV", require_plan=True)

    def test_restore_manager_deployment_output_rejects_state_for_another_twin(self) -> None:
        deployment_dir = self.manager_deployments / "PV"
        self.write_manager_config_set(deployment_dir / "input", "PV")
        self.write_manager_redeployment_state(deployment_dir / "output", "Battery", include_plan=True)

        with self.assertRaises(SystemExit):
            staging.restore_manager_deployment_output("PV", require_plan=True)

    def test_save_manager_deployment_plan_copies_current_output_snapshot(self) -> None:
        self.write_manager_config_set(self.manager_input, "PV")
        self.write_json(self.manager_output / "PV_federation_input.json", {"name": "PV"})
        self.write_manager_redeployment_state(self.manager_output, "PV", include_plan=True)

        saved_plan = staging.save_manager_deployment_plan()

        self.assertEqual(
            saved_plan,
            self.manager_deployments
            / "PV"
            / "output"
            / staging.MANAGER_STATE_DIR_NAME
            / staging.MANAGER_STATE_PLAN_FILE_NAME,
        )
        self.assertTrue(saved_plan.is_file())
        self.assertTrue((saved_plan.parents[1] / "PV_federation_input.json").is_file())

    def test_invalidate_manager_deployment_plan_removes_current_and_saved_plans(self) -> None:
        deployment_dir = self.manager_deployments / "PV"
        self.write_manager_config_set(deployment_dir / "input", "PV")
        current_state = self.write_manager_redeployment_state(self.manager_output, "PV", include_plan=True)
        saved_state = self.write_manager_redeployment_state(deployment_dir / "output", "PV", include_plan=True)

        staging.invalidate_manager_deployment_plan("pv")

        self.assertFalse((current_state / staging.MANAGER_STATE_PLAN_FILE_NAME).exists())
        self.assertFalse((saved_state / staging.MANAGER_STATE_PLAN_FILE_NAME).exists())
        self.assertTrue((current_state / staging.MANAGER_STATE_METADATA_FILE_NAME).is_file())
        self.assertTrue((saved_state / staging.MANAGER_STATE_METADATA_FILE_NAME).is_file())

    def test_simulator_project_name_is_deterministic_and_safe(self) -> None:
        project_name = staging.simulator_project_name("dtc-y-03")

        self.assertEqual(project_name, staging.simulator_project_name("dtc-y-03"))
        self.assertRegex(project_name, r"^cloud-dtc-simulator-dtc-y-03-[0-9a-f]{8}$")
        self.assertEqual(project_name, project_name.lower())

    def test_simulator_state_can_be_written_read_listed_and_deleted(self) -> None:
        input_dir = self.manager_deployments / "PV" / "input"
        self.write_manager_config_set(input_dir, "PV")

        state = staging.write_simulator_state(
            "PV",
            project_name="cloud-dtc-simulator-pv-12345678",
            host_port=5000,
            input_dir=input_dir,
        )

        self.assertEqual(state["digital_twin_name"], "PV")
        self.assertEqual(state["url"], "http://127.0.0.1:5000")
        self.assertEqual(staging.read_simulator_state("pv")["project_name"], "cloud-dtc-simulator-pv-12345678")
        self.assertEqual([state["digital_twin_name"] for state in staging.list_simulator_states()], ["PV"])

        staging.delete_simulator_state("PV")

        self.assertIsNone(staging.read_simulator_state("PV"))
        self.assertEqual(staging.list_simulator_states(), [])

    def test_list_simulator_states_does_not_require_valid_deployment_input(self) -> None:
        self.write_json(
            self.manager_deployments / "PV" / "simulator.json",
            {
                "digital_twin_name": "PV",
                "project_name": "cloud-dtc-simulator-pv-12345678",
                "host_port": 5000,
                "url": "http://127.0.0.1:5000",
                "input_dir": "pipeline/digital-twin-manager/deployments/PV/input",
            },
        )

        self.assertEqual([state["digital_twin_name"] for state in staging.list_simulator_states()], ["PV"])

    def test_allocate_simulator_host_port_skips_ports_from_state(self) -> None:
        input_dir = self.manager_deployments / "PV" / "input"
        self.write_manager_config_set(input_dir, "PV")
        staging.write_simulator_state(
            "PV",
            project_name="cloud-dtc-simulator-pv-12345678",
            host_port=5000,
            input_dir=input_dir,
        )

        original_port_check = staging._is_local_port_available
        staging._is_local_port_available = lambda port: True
        try:
            self.assertEqual(staging.allocate_simulator_host_port(start=5000, end=5001), 5001)
        finally:
            staging._is_local_port_available = original_port_check

    def test_require_manager_deployment_simulator_input_fails_when_missing(self) -> None:
        with self.assertRaises(SystemExit):
            staging.require_manager_deployment_simulator_input("PV")

    def test_stage_federation_inputs_uses_only_twins_from_fedtwin(self) -> None:
        self.write_fedtwin(["PV.production", "Battery.status"])
        self.write_broker_config()
        self.write_json(self.manager_deployments / "PV" / "output" / "PV_federation_input.json", {"name": "PV"})
        self.write_json(self.manager_deployments / "Battery" / "output" / "Battery_federation_input.json", {"name": "Battery"})
        self.write_json(self.manager_deployments / "Unused" / "output" / "Unused_federation_input.json", {"name": "Unused"})
        self.write_json(self.federation_input / "strategyInputs" / "stale_federation_input.json", {"name": "stale"})

        staged = staging.stage_federation_inputs_from_deployments()

        self.assertEqual(
            [path.name for path in staged],
            ["PV_federation_input.json", "Battery_federation_input.json"],
        )
        self.assertTrue((self.federation_input / "strategyInputs" / "PV_federation_input.json").is_file())
        self.assertTrue((self.federation_input / "strategyInputs" / "Battery_federation_input.json").is_file())
        self.assertFalse((self.federation_input / "strategyInputs" / "Unused_federation_input.json").exists())
        self.assertFalse((self.federation_input / "strategyInputs" / "stale_federation_input.json").exists())

    def test_stage_federation_inputs_fails_when_required_artifact_is_missing(self) -> None:
        self.write_fedtwin(["PV.production", "Battery.status"])
        self.write_broker_config()
        self.write_json(self.manager_deployments / "PV" / "output" / "PV_federation_input.json", {"name": "PV"})

        with self.assertRaises(SystemExit):
            staging.stage_federation_inputs_from_deployments()

    def test_prepare_local_grafana_stage_writes_runtime_state(self) -> None:
        with patch.dict("os.environ", {"LOCAL_GRAFANA_HOST_PORT": "3030"}, clear=True):
            state = staging.prepare_local_grafana_stage()

        saved_state = json.loads(self.grafana_state.read_text(encoding="utf-8"))
        self.assertEqual(saved_state, state)
        self.assertEqual(state["project_name"], "cloud-dtc-grafana")
        self.assertEqual(state["url"], "http://127.0.0.1:3030")
        self.assertEqual(staging.read_local_grafana_state(), state)


if __name__ == "__main__":
    unittest.main()
