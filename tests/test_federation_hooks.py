from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.orchestrator import federation_hooks as hooks
from scripts.orchestrator import pipeline

REPO = Path(__file__).resolve().parents[1]
PV = "dtc-PVWeatherStrategy"
BATTERY = "dtc-BatteryChargerDecisionStrategy"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    fed_input = tmp_path / "pipeline/fed-sysml/input"
    fed_output = tmp_path / "pipeline/fed-sysml/output"
    fed_input.mkdir(parents=True)
    fed_output.mkdir(parents=True)
    monkeypatch.setattr(hooks, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hooks, "FEDERATION_INPUT_DIR", fed_input)
    monkeypatch.setattr(hooks, "FEDERATION_OUTPUT_DIR", fed_output)
    monkeypatch.setattr(pipeline, "FEDERATION_OUTPUT_DIR", fed_output)
    monkeypatch.setattr(pipeline, "FEDERATION_TERRAFORM_MAIN_FILE", fed_output / "main.tf")
    monkeypatch.setattr(pipeline, "FEDERATION_TERRAFORM_PLAN_PATH", fed_output / "fed-sysml.tfplan")
    (tmp_path / "scripts").mkdir()
    for script in ["resolve_common.py", *(h.before_generate or h.after_apply for h in hooks.HOOKS.values())]:
        shutil.copy2(REPO / "scripts" / script, tmp_path / "scripts" / script)
    for template in (REPO / "demo-code/microgrid/federation").glob("*/lambda_function.py.template"):
        target = tmp_path / template.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, target)
    shutil.copy2(REPO / "pipeline/fed-sysml/input/fedtwin.microgrid.example.json", fed_input / "fedtwin.json")
    write_json(fed_input / "brokerConfig.json", {})
    return tmp_path


def select(*names):
    write_json(hooks.FEDERATION_INPUT_DIR / "fedtwin.json", {
        "fedTwins": [{"name": "test", "newStrategies": [{"name": name} for name in names]}],
    })


def deploy(repo, twin):
    properties = {
        "dtcBattery": ["charge", "isPlugged", "generatedPower", "greenEnergyPercentage", "maxPower",
                       "maxChargingPower", "maxDischargingPower", "totalCapacity"],
        "dtcGrid": ["currentElectricityPrice"],
        "dtcPV": ["production", "maxPower"],
        "dtcWeather": ["hour00"],
        "dtcCharger": ["actChargeEV", "maxPower"],
    }[twin]
    directory = repo / "pipeline/digital-twin-manager/deployments" / twin
    write_json(directory / "input/config_iot_devices.json", [{
        "id": f"{twin}-device", "properties": [{"name": name, "initValue": 10} for name in properties],
    }])
    write_json(directory / "input/config_hierarchy.json", [{
        "id": f"{twin}-entity", "children": [{"iotDeviceId": f"{twin}-device", "name": "component"}],
    }])
    write_json(directory / "output" / f"{twin}_federation_input.json", {
        "region": "eu-west-1", "hot_reader_arn": f"{twin}-reader", "twinmaker_workspace_id": f"{twin}-workspace",
    })


def deploy_all(repo):
    for twin in ("dtcWeather", "dtcPV", "dtcGrid", "dtcBattery", "dtcCharger"):
        deploy(repo, twin)


def generate(manifest):
    (hooks.FEDERATION_OUTPUT_DIR / "main.tf").write_text("\n".join(
        f'resource "aws_lambda_function" "{name}_pipeline" {{}}'
        for name in manifest["strategies"]
    ), encoding="utf-8")
    staged = []
    if BATTERY in manifest["strategies"]:
        source = hooks.REPO_ROOT / "pipeline/digital-twin-manager/deployments/dtcBattery/output/dtcBattery_federation_input.json"
        target = hooks.FEDERATION_INPUT_DIR / "strategyInputs" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        staged.append(target)
    hooks.save_federation_hooks(manifest, staged)


def prepared(repo):
    deploy_all(repo)
    with patch.object(hooks, "_run_helper"):
        manifest = hooks.prepare_federation_hooks(for_generation=True)
    generate(manifest)
    return manifest


def test_prepare_resolves_all_four_targets_before_charger_exists(repo):
    deploy(repo, "dtcBattery")
    hooks.prepare_federation_hooks()
    generated = list((repo / "demo-code/microgrid/federation").glob("*/lambda_function.py"))
    assert len(generated) == 4
    for source in generated:
        assert '"dtcBattery-device"' in source.read_text()
        assert "__BATTERY_" not in source.read_text()
    assert not (hooks.FEDERATION_OUTPUT_DIR / "main.tf").exists()


def test_selected_names_are_deduplicated_and_unrelated_strategies_do_not_run_helpers(repo):
    select(PV, PV, "MEPSO", BATTERY)
    assert hooks.selected_strategies() == [PV, BATTERY]
    select("MEPSO")
    with patch.object(hooks, "_run_helper") as helper:
        manifest = hooks.prepare_federation_hooks(for_generation=True)
        generate(manifest)
        hooks.configure_federation_hooks()
    helper.assert_not_called()


def test_generation_requires_passive_weather_before_running_any_helper(repo):
    select(PV)
    deploy(repo, "dtcPV")
    with patch.object(hooks, "_run_helper") as helper, pytest.raises(SystemExit):
        hooks.prepare_federation_hooks(for_generation=True)
    helper.assert_not_called()


def test_generation_runs_local_checks_and_resolvers_without_aws(repo):
    deploy_all(repo)
    # Real subprocesses execute --check for both AWS helpers, without credentials.
    manifest = hooks.prepare_federation_hooks(for_generation=True)
    generate(manifest)
    assert hooks.validate_federation_hooks()["terraform_applied"] is False


@pytest.mark.parametrize("change", ["battery", "config", "terraform", "added_file", "staged_input"])
def test_changed_inputs_or_output_block_configuration(repo, change):
    manifest = prepared(repo)
    hooks.mark_federation_applied(manifest, applied=True)
    targets = {
        "battery": repo / hooks._BATTERY_DEVICES[0],
        "config": hooks.FEDERATION_INPUT_DIR / "fedtwin.json",
        "terraform": hooks.FEDERATION_OUTPUT_DIR / "main.tf",
        "added_file": hooks.FEDERATION_OUTPUT_DIR / "extra.tf",
        "staged_input": hooks.FEDERATION_INPUT_DIR / "strategyInputs/dtcBattery_federation_input.json",
    }
    with targets[change].open("a", encoding="utf-8") as source:
        source.write("\n ")
    with patch.object(hooks, "_run_helper") as helper, pytest.raises(SystemExit):
        hooks.configure_federation_hooks()
    helper.assert_not_called()


def test_configuration_failure_keeps_applied_state_and_can_be_retried(repo, capsys):
    manifest = prepared(repo)
    hooks.mark_federation_applied(manifest, applied=True)
    with patch.object(hooks, "_run_helper", side_effect=[None, SystemExit(3)]), pytest.raises(SystemExit):
        hooks.configure_federation_hooks()
    assert "Terraform was applied" in capsys.readouterr().err
    saved = hooks.validate_federation_hooks()
    assert saved["terraform_applied"] is True
    assert saved["configured"] is False
    with patch.object(hooks, "_run_helper") as helper:
        hooks.configure_federation_hooks()
    assert [c.args[0] for c in helper.call_args_list] == [
        "federate_pv_weather.py", "federate_battery_charger_decision.py",
    ]
    assert hooks.validate_federation_hooks()["configured"] is True


def test_configuration_requires_successful_apply(repo):
    prepared(repo)
    with patch.object(hooks, "_run_helper") as helper, pytest.raises(SystemExit):
        hooks.configure_federation_hooks()
    helper.assert_not_called()


def test_missing_manifest_requires_regeneration_only_for_registered_output(repo):
    prepared(repo)
    hooks.invalidate_federation_hooks()
    with pytest.raises(SystemExit):
        hooks.validate_federation_hooks()
    (hooks.FEDERATION_OUTPUT_DIR / "main.tf").write_text('resource "aws_lambda_function" "other_pipeline" {}')
    assert hooks.validate_federation_hooks() is None


def test_pipeline_applies_before_configuration_and_does_not_configure_failed_apply(repo):
    prepared(repo)
    compose = repo / "docker-compose.yaml"
    compose.touch()
    pipeline.FEDERATION_TERRAFORM_PLAN_PATH.write_text("saved plan")
    config = SimpleNamespace(compose_file=compose, compose_profiles=(), build_images=False)
    events = []
    with (
        patch.object(pipeline, "run_fed_sysml_terraform_apply_plan", side_effect=lambda **kw: events.append("apply")),
        patch.object(hooks, "_run_helper", side_effect=lambda script: events.append(script)),
    ):
        pipeline.run_fed_sysml_terraform_apply_saved_plan_stage(config)
    assert events == ["apply", "federate_pv_weather.py", "federate_battery_charger_decision.py"]
    with (
        patch.object(pipeline, "run_fed_sysml_terraform_apply_plan", side_effect=SystemExit(1)),
        patch.object(hooks, "_run_helper") as helper,
        pytest.raises(SystemExit),
    ):
        pipeline.run_fed_sysml_terraform_apply_saved_plan_stage(config)
    helper.assert_not_called()
    assert hooks.validate_federation_hooks()["terraform_applied"] is False


def test_stale_inputs_block_terraform_apply_itself(repo):
    prepared(repo)
    compose = repo / "docker-compose.yaml"
    compose.touch()
    pipeline.FEDERATION_TERRAFORM_PLAN_PATH.write_text("saved plan")
    config = SimpleNamespace(compose_file=compose)
    (repo / hooks._BATTERY_DEVICES[0]).write_text("[]")
    with patch.object(pipeline, "run_fed_sysml_terraform_apply_plan") as apply, pytest.raises(SystemExit):
        pipeline.run_fed_sysml_terraform_apply_saved_plan_stage(config)
    apply.assert_not_called()


def test_environment_uses_dotenv_with_process_precedence(repo, monkeypatch):
    (repo / ".env").write_text("HOOK_TEST_A=from_file\nHOOK_TEST_B=from_file\n", encoding="utf-8")
    monkeypatch.setenv("HOOK_TEST_A", "from_process")
    monkeypatch.delenv("HOOK_TEST_B", raising=False)
    environment = hooks._script_environment()
    assert "HOOK_TEST_A" not in environment
    assert environment["HOOK_TEST_B"] == "from_file"


@pytest.mark.parametrize("action", ["none", "apply"])
def test_generation_prepares_before_packaging_and_automatic_apply_uses_same_hooks(repo, action):
    deploy_all(repo)
    compose = repo / "docker-compose.yaml"
    compose.touch()
    config = SimpleNamespace(
        compose_file=compose, compose_profiles=(), build_images=False, clean_stage=True,
        show_container_logs=False, fed_sysml_terraform_action=action,
        fed_sysml_terraform_auto_approve=True,
    )
    events = []

    def generator(**kwargs):
        events.append("generate")
        (hooks.FEDERATION_OUTPUT_DIR / "main.tf").write_text("\n".join(
            f'resource "aws_lambda_function" "{name}_pipeline" {{}}' for name in hooks.selected_strategies()
        ))

    def plan(**kwargs):
        events.append("plan")
        pipeline.FEDERATION_TERRAFORM_PLAN_PATH.write_text("saved plan")

    with (
        patch.object(hooks, "_run_helper", side_effect=lambda script, **kw: events.append((script, kw.get("check", False)))),
        patch.object(pipeline, "prepare_federation_stage"),
        patch.object(pipeline, "stage_federation_inputs_from_deployments", return_value=[]),
        patch.object(pipeline, "run_fed_sysml", side_effect=generator),
        patch.object(pipeline, "run_fed_sysml_terraform_init"),
        patch.object(pipeline, "run_fed_sysml_terraform_plan", side_effect=plan),
        patch.object(pipeline, "run_fed_sysml_terraform_apply_plan", side_effect=lambda **kw: events.append("apply")),
    ):
        pipeline.run_federation_stage(config)
    expected_resolvers = {h.before_generate for h in hooks.HOOKS.values() if h.before_generate}
    assert {e[0] for e in events[:events.index("generate")] if not e[1]} == expected_resolvers
    if action == "apply":
        assert events[-4:] == ["plan", "apply", ("federate_pv_weather.py", False), ("federate_battery_charger_decision.py", False)]
    else:
        assert events[-1] == "generate"
        assert hooks.validate_federation_hooks()["terraform_applied"] is False


@pytest.mark.parametrize("action", ["plan", "destroy"])
def test_plan_and_destroy_never_run_aws_helpers(repo, action):
    prepared(repo)
    compose = repo / "docker-compose.yaml"
    compose.touch()
    config = SimpleNamespace(
        compose_file=compose, compose_profiles=(), build_images=False,
        fed_sysml_terraform_action=action, fed_sysml_terraform_auto_approve=True,
    )
    with (
        patch.object(hooks, "_run_helper") as helper,
        patch.object(pipeline, "run_fed_sysml_terraform_init"),
        patch.object(pipeline, "run_fed_sysml_terraform_plan"),
        patch.object(pipeline, "run_fed_sysml_terraform_destroy"),
    ):
        pipeline.run_fed_sysml_terraform_stage(config)
    helper.assert_not_called()


def test_regeneration_updates_target_after_battery_device_changes(repo):
    deploy(repo, "dtcBattery")
    hooks.prepare_federation_hooks()
    devices = repo / hooks._BATTERY_DEVICES[0]
    data = json.loads(devices.read_text())
    data[0]["id"] = "new-battery-device"
    write_json(devices, data)
    hooks.prepare_federation_hooks()
    for source in (repo / "demo-code/microgrid/federation").glob("*/lambda_function.py"):
        assert '"new-battery-device"' in source.read_text()
        assert '"dtcBattery-device"' not in source.read_text()


def test_single_selected_federation_only_configures_its_own_lambda(repo):
    select(PV)
    deploy(repo, "dtcPV")
    deploy(repo, "dtcWeather")
    with patch.object(hooks, "_run_helper"):
        manifest = hooks.prepare_federation_hooks(for_generation=True)
    generate(manifest)
    hooks.mark_federation_applied(manifest, applied=True)
    with patch.object(hooks, "_run_helper") as helper:
        hooks.configure_federation_hooks()
    helper.assert_called_once_with("federate_pv_weather.py")
