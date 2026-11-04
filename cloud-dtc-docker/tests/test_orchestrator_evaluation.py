import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.orchestrator import app, docker_compose, evaluation


@pytest.mark.parametrize("command,action,evaluation_type,twin,config_path", [
    ("evaluate roundtrip MGridICSA", "run", "roundtrip", "MGridICSA", None),
    ('plan evaluation roundtrip MGridICSA "settings with spaces.json"', "plan", "roundtrip", "MGridICSA", "settings with spaces.json"),
    ('evaluate roundtrip MGridICSA "D:\\custom folder\\roundtrip.json"', "run", "roundtrip", "MGridICSA", "D:\\custom folder\\roundtrip.json"),
    ("evaluate mqtt-twinmaker CheckWatt", "run", "mqtt-twinmaker", "CheckWatt", None),
    ("plan evaluation mqtt-twinmaker MGridICSA", "plan", "mqtt-twinmaker", "MGridICSA", None),
])
def test_evaluation_command_preserves_target_case_and_quoted_paths(command, action, evaluation_type, twin, config_path):
    request = evaluation.parse_evaluation_command(command)
    assert request.action == action
    assert request.evaluation_type == evaluation_type
    assert request.twin_name == twin
    assert request.config_file == (Path(config_path) if config_path else None)


def test_other_pipeline_commands_are_not_captured():
    assert evaluation.parse_evaluation_command("plan digital-twin-manager MGridICSA") is None
    assert evaluation.parse_evaluation_command("continue sysml-v2 MGridICSA.sysml") is None


@pytest.mark.parametrize("command", ["evaluate", "evaluate roundtrip", "plan evaluation", "evaluate ../invalid MGridICSA"])
def test_incomplete_or_invalid_evaluation_commands_fail_clearly(command):
    with pytest.raises(ValueError):
        evaluation.parse_evaluation_command(command)


def test_evaluation_dispatch_precedes_generic_manager_plan():
    with (
        patch.object(app, "handle_evaluation_command", return_value=True) as handle,
        patch.object(app, "_select_manager_deployment") as select,
    ):
        app._handle_command(object(), "plan evaluation roundtrip MGridICSA", object())
    handle.assert_called_once()
    select.assert_not_called()


def test_failed_evaluation_does_not_stop_the_pipeline_watcher():
    with patch.object(evaluation, "run_evaluation_stage", side_effect=SystemExit(1)):
        assert evaluation.handle_evaluation_command(object(), "evaluate roundtrip MGridICSA") is True


def test_docker_runner_mounts_only_the_selected_deployment_and_config(tmp_path):
    with patch.object(docker_compose, "run_command") as run:
        docker_compose.run_digital_twin_evaluation(
            compose_file=Path("docker-compose.yaml"), profiles=("pipeline",),
            action="run", evaluation_type="roundtrip",
            deployment_dir=tmp_path / "MGridICSA", evaluation_config=tmp_path / "roundtrip.json",
            output_dir=tmp_path / "reports", show_container_logs=True,
        )
    command = run.call_args.args[0]
    assert command[command.index("--profile", 6) + 1] == "evaluation"
    assert "--no-deps" in command
    assert command[command.index("digital-twin-evaluation") + 1:][:2] == ["run", "roundtrip"]
    assert command[-2:] == ["--output", "/evaluation/results"]
    env = run.call_args.kwargs["env"]
    assert env["EVALUATION_DEPLOYMENT_HOST_DIR"] == (tmp_path / "MGridICSA").resolve().as_posix()
    assert env["EVALUATION_CONFIG_HOST_FILE"] == (tmp_path / "roundtrip.json").resolve().as_posix()


def test_offline_plan_does_not_pass_a_run_only_output_option(tmp_path):
    with patch.object(docker_compose, "run_command") as run:
        docker_compose.run_digital_twin_evaluation(
            compose_file=Path("docker-compose.yaml"), profiles=(), action="plan",
            evaluation_type="roundtrip", deployment_dir=tmp_path, evaluation_config=tmp_path / "eval.json",
            output_dir=tmp_path / "reports", show_container_logs=False,
        )
    assert "--output" not in run.call_args.args[0]


def test_missing_applied_state_fails_before_docker_runs(tmp_path):
    request = evaluation.parse_evaluation_command("evaluate roundtrip MGridICSA")
    with (
        patch.object(evaluation, "MANAGER_DEPLOYMENTS_DIR", tmp_path),
        patch.object(evaluation, "resolve_manager_deployment_name", return_value="MGridICSA"),
        patch.object(evaluation, "run_digital_twin_evaluation") as run,
        pytest.raises(SystemExit),
    ):
        evaluation.run_evaluation_stage(SimpleNamespace(), request)
    run.assert_not_called()


def test_a_plan_saved_under_a_new_twin_does_not_evaluate_the_old_twin(tmp_path, capsys):
    state = tmp_path / "MGridICSA/output/.digital-twin-manager-state"
    (state / "configs").mkdir(parents=True)
    for name in ("config.json", "config_hierarchy.json", "config_iot_devices.json"):
        (state / "configs" / name).write_text("{}")
    (state / "metadata.json").write_text(json.dumps({"digitalTwinName": "OldTwin"}))
    request = evaluation.parse_evaluation_command("evaluate roundtrip MGridICSA")
    with (
        patch.object(evaluation, "MANAGER_DEPLOYMENTS_DIR", tmp_path),
        patch.object(evaluation, "resolve_manager_deployment_name", return_value="MGridICSA"),
        patch.object(evaluation, "run_digital_twin_evaluation") as run,
        pytest.raises(SystemExit),
    ):
        evaluation.run_evaluation_stage(SimpleNamespace(), request)
    assert "belongs to" in capsys.readouterr().err
    run.assert_not_called()


@pytest.mark.parametrize("exit_code", [0, 1])
def test_run_reports_the_absolute_host_directory_even_when_measurements_fail(tmp_path, capsys, exit_code):
    deployments = tmp_path / "deployments"
    state = deployments / "MGridICSA/output/.digital-twin-manager-state"
    (state / "configs").mkdir(parents=True)
    (state / "metadata.json").write_text(json.dumps({"digitalTwinName": "MGridICSA"}))
    for name in ("config.json", "config_hierarchy.json", "config_iot_devices.json"):
        (state / "configs" / name).write_text("{}")
    settings = tmp_path / "MGridICSA.mqtt.json"
    settings.write_text("{}")
    output = tmp_path / "reports"
    run_id = "0fd9f839629b4b55b1c3f754309c0816"

    def run_with_report(**kwargs):
        directory = kwargs["output_dir"] / "MGridICSA" / run_id
        directory.mkdir(parents=True)
        (directory / "summary.json").write_text(json.dumps({"successful": exit_code == 0}))
        (directory / "measurements.csv").write_text("status\n")
        if exit_code:
            raise SystemExit(exit_code)

    config = SimpleNamespace(compose_file="docker-compose.yaml", compose_profiles=(), show_container_logs=True)
    command = f'evaluate mqtt MGridICSA "{settings}"'
    with (
        patch.object(evaluation, "MANAGER_DEPLOYMENTS_DIR", deployments),
        patch.object(evaluation, "EVALUATION_OUTPUT_DIR", output),
        patch.object(evaluation, "run_digital_twin_evaluation", side_effect=run_with_report),
    ):
        assert evaluation.handle_evaluation_command(config, command)

    assert f"Evaluation reports (host): {(output / 'MGridICSA').resolve()}" in capsys.readouterr().out
    assert (output / "MGridICSA" / run_id / "summary.json").is_file()
    assert (output / "MGridICSA" / run_id / "measurements.csv").is_file()
