from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from .cli import LaunchOptions
from .config import PipelineConfig, load_pipeline_config, print_run_config
from .docker_compose import remove_infrastructure, start_infrastructure
from .file_watcher import FileChange, OutputFileWatcher
from .evaluation import handle_evaluation_command
from .federation_hooks import configure_federation_hooks, prepare_federation_hooks
from .pipeline import (
    remove_all_cloud_deployer_test_simulators_stage,
    remove_cloud_deployer_test_simulator_stage,
    run_digital_twin_manager_apply_stage,
    run_digital_twin_manager_destroy_stage,
    run_digital_twin_manager_plan_stage,
    start_cloud_deployer_test_simulator_stage,
    start_local_grafana_stage,
    stop_local_grafana_stage,
    run_digital_twin_manager_deploy_stage,
    run_fed_sysml_terraform_apply_saved_plan_stage,
    run_fed_sysml_terraform_plan_stage,
    run_fed_sysml_terraform_stage,
    run_federation_stage,
    run_pipeline,
    run_staged_converter_stage,
)
from .pipeline_paths import converter_label, relative_to_repo, resolve_repo_path
from .staging import (
    list_manager_deployments,
    list_simulator_states,
    list_staged_converter_inputs,
    read_manager_input_twin_name,
)
from .user_input import UserInput


class StopRequested(Exception):
    pass


DigitalTwinManagerAction = Literal["deploy", "plan", "apply"]


CONTINUE_DIGITAL_TWIN_MANAGER_ALIASES = (
    ["digital", "twin"],
    ["digital", "twin", "manager"],
    ["deploy", "to", "aws"],
    ["continue", "digital", "twin"],
    ["continue", "digital", "twin", "manager"],
    ["continue", "with", "digital", "twin"],
    ["continue", "with", "digital", "twin", "manager"],
    ["continue", "deploy", "to", "aws"],
    ["continue", "with", "deploy", "to", "aws"],
)

DESTROY_DIGITAL_TWIN_MANAGER_ALIASES = (
    ["destroy"],
    ["destroy", "aws"],
    ["destroy", "deploy"],
    ["destroy", "deployment"],
    ["destroy", "digital", "twin"],
    ["destroy", "digital", "twin", "manager"],
    ["digital", "twin", "destroy"],
    ["digital", "twin", "manager", "destroy"],
    ["destroy", "deployed", "digital", "twin"],
    ["destroy", "deployed", "digital", "twin", "manager"],
)

PLAN_DIGITAL_TWIN_MANAGER_ALIASES = (
    ["plan"],
    ["plan", "digital", "twin"],
    ["plan", "digital", "twin", "manager"],
    ["digital", "twin", "plan"],
    ["digital", "twin", "manager", "plan"],
)

APPLY_DIGITAL_TWIN_MANAGER_ALIASES = (
    ["apply"],
    ["apply", "digital", "twin"],
    ["apply", "digital", "twin", "manager"],
    ["digital", "twin", "apply"],
    ["digital", "twin", "manager", "apply"],
)

CONTINUE_SYSML_V1_ALIASES = (
    ["sysml", "v1"],
    ["continue", "sysml", "v1"],
    ["continue", "with", "sysml", "v1"],
    ["digital", "twin", "profile", "sysml", "v1"],
    ["continue", "digital", "twin", "profile", "sysml", "v1"],
    ["continue", "with", "digital", "twin", "profile", "sysml", "v1"],
)

CONTINUE_SYSML_V2_ALIASES = (
    ["sysml", "v2"],
    ["continue", "sysml", "v2"],
    ["continue", "with", "sysml", "v2"],
    ["digital", "twin", "profile", "sysml", "v2"],
    ["continue", "digital", "twin", "profile", "sysml", "v2"],
    ["continue", "with", "digital", "twin", "profile", "sysml", "v2"],
)

START_SIMULATOR_ALIASES = (
    ["simulator"],
    ["test", "simulator"],
    ["cloud", "deployer", "test", "simulator"],
    ["cloud", "deployer", "simulator"],
    ["start", "simulator"],
    ["start", "test", "simulator"],
    ["start", "cloud", "deployer", "test", "simulator"],
    ["run", "simulator"],
    ["run", "test", "simulator"],
    ["run", "cloud", "deployer", "test", "simulator"],
    ["continue", "simulator"],
    ["continue", "test", "simulator"],
    ["continue", "cloud", "deployer", "test", "simulator"],
)

STOP_SIMULATOR_ALIASES = (
    ["stop", "simulator"],
    ["stop", "test", "simulator"],
    ["stop", "cloud", "deployer", "test", "simulator"],
    ["stop", "cloud", "deployer", "simulator"],
    ["remove", "simulator"],
    ["remove", "test", "simulator"],
    ["remove", "cloud", "deployer", "test", "simulator"],
    ["remove", "cloud", "deployer", "simulator"],
)

START_GRAFANA_ALIASES = (
    ["grafana"],
    ["start", "grafana"],
    ["run", "grafana"],
)

STOP_GRAFANA_ALIASES = (
    ["stop", "grafana"],
    ["remove", "grafana"],
)


def run_app(options: LaunchOptions) -> None:
    config = load_pipeline_config(options.config_file)
    if options.auto_run:
        config = config.with_auto_run(True)
    if options.remove_infrastructure_on_exit:
        config = config.with_remove_infrastructure_on_exit(True)

    compose_file = resolve_repo_path(config.compose_file)
    watch_directory = resolve_repo_path(config.watch.directory)

    print(f"Loaded config: {relative_to_repo(resolve_repo_path(options.config_file))}")
    try:
        start_infrastructure(
            compose_file=compose_file,
            profiles=config.compose_profiles,
            build_images=config.build_images,
            show_container_logs=config.show_container_logs,
        )
        _print_infrastructure_ready()

        watcher = OutputFileWatcher(watch_directory, settle_seconds=config.watch.settle_seconds)
        watcher.reset()

        user_input = UserInput()
        user_input.start()

        print(f"\nWatching {relative_to_repo(watch_directory)} for .xml, .xmi, and .sysml exports.")
        print("Type 'continue sysml-v1' or 'continue sysml-v2 [file]' to run a staged converter input.")
        print("Type 'continue digital-twin-manager [name]' to deploy a saved digital twin input.")
        print("Type 'plan digital-twin-manager [name]' to plan changes to a saved digital twin deployment.")
        print("Type 'apply digital-twin-manager [name]' to apply its saved digital twin plan.")
        print("Type 'destroy digital-twin-manager [name]' to destroy a saved digital twin deployment.")
        print("Type 'continue fed-sysml' to resume from the fed-sysml step.")
        print("Type 'fed prepare' to resolve federation targets before deploying the last twin.")
        print("Type 'fed configure' to retry configuration after a successful federation apply.")
        print("Type 'fed terraform plan' to plan the generated fed-sysml Terraform output.")
        print("Type 'fed terraform apply' to apply the generated fed-sysml Terraform output.")
        print("Type 'fed terraform destroy' to destroy the fed-sysml Terraform resources.")
        print("Type 'start simulator [name]' to start cloud-deployer-test-simulator for a saved digital twin.")
        print("Type 'stop simulator [name]' to stop and remove a running cloud-deployer-test-simulator.")
        print("Type 'start grafana' to start local Grafana.")
        print("Type 'stop grafana' to stop and remove local Grafana.")
        print("Type 'plan evaluation <type> <twin> [config]' to inspect an evaluation without AWS calls.")
        print("Type 'evaluate <type> <twin> [config]' to run an evaluation after deploy.")
        print("Type 'exit' and press Enter to stop.")
        if config.auto_run:
            print("Auto-run is enabled.")
        if config.remove_infrastructure_on_exit:
            print("Infrastructure containers will be removed when the watcher exits.")

        _watch_forever(config, watcher, user_input)
    except StopRequested:
        print("\nStopping run loop.")
    except KeyboardInterrupt:
        print("\nStopping run loop.")
    finally:
        _remove_cloud_deployer_test_simulator_safely(config)
        if config.remove_infrastructure_on_exit:
            remove_infrastructure(
                compose_file=compose_file,
                profiles=config.compose_profiles,
                show_container_logs=config.show_container_logs,
            )
        else:
            print("Infrastructure Docker services remain running.")


def _watch_forever(config: PipelineConfig, watcher: OutputFileWatcher, user_input: UserInput) -> None:
    while True:
        command = user_input.get_line(timeout=config.watch.poll_interval_seconds)
        if command is not None:
            _handle_command(config, command, user_input)

        for change in watcher.poll():
            _handle_file_change(config, change, user_input)


def _handle_file_change(config: PipelineConfig, change: FileChange, user_input: UserInput) -> None:
    print(
        "\nDetected {event_type} export: {path} ({size} bytes, modified {modified})".format(
            event_type=change.event_type,
            path=relative_to_repo(change.path),
            size=change.size,
            modified=datetime.fromtimestamp(change.modified_at).strftime("%Y-%m-%d %H:%M:%S"),
        )
    )
    print_run_config(config, source=change.path, converter=change.converter)

    if config.auto_run:
        print("Auto-run accepted this change.")
        run_config = config
        if config.deploy_to_aws is None:
            print("AWS deploy is unset; auto-run will keep deploy disabled.")
            run_config = config.with_deploy_to_aws(False)
        _run_pipeline_safely(run_config, change.path, change.converter)
        return

    if not _prompt_yes_no(user_input, "Run pipeline for this export? [y/N] "):
        print("Skipped pipeline run.")
        return

    run_config = config
    deploy_to_aws = config.deploy_to_aws
    if deploy_to_aws is None:
        deploy_to_aws = _prompt_yes_no(user_input, "Deploy to AWS for this export? [y/N] ")
        run_config = run_config.with_deploy_to_aws(deploy_to_aws)
        print(f"AWS deploy for this run: {'enabled' if deploy_to_aws else 'disabled'}.")

    if deploy_to_aws:
        run_federation = _prompt_yes_no(user_input, "Run federation workflow for this export? [y/N] ")
        run_config = run_config.with_run_federation_workflow(run_federation)
        print(f"Federation workflow for this run: {'enabled' if run_federation else 'disabled'}.")
    elif config.deploy_to_aws is None:
        run_config = run_config.with_run_federation_workflow(False)
    _run_pipeline_safely(run_config, change.path, change.converter)


def _run_pipeline_safely(config: PipelineConfig, source: Path, converter: str) -> None:
    try:
        run_pipeline(config, source=source, converter=converter)
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nPipeline failed with exit code {code}. Watching will continue.")


def _run_federation_safely(config: PipelineConfig) -> bool:
    try:
        run_federation_stage(config)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nFederation step failed with exit code {code}. Watching will continue.")
        return False


def _run_digital_twin_manager_action_safely(
    config: PipelineConfig,
    action: DigitalTwinManagerAction,
    deployment_name: str | None = None,
) -> bool:
    try:
        match action:
            case "deploy":
                run_digital_twin_manager_deploy_stage(config, deployment_name=deployment_name)
            case "plan":
                run_digital_twin_manager_plan_stage(config, deployment_name=deployment_name)
            case "apply":
                run_digital_twin_manager_apply_stage(config, deployment_name=deployment_name)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nDigital twin manager {action} failed with exit code {code}. Watching will continue.")
        return False


def _run_digital_twin_manager_destroy_safely(config: PipelineConfig, deployment_name: str | None = None) -> bool:
    try:
        run_digital_twin_manager_destroy_stage(config, deployment_name=deployment_name)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nDigital twin manager destroy failed with exit code {code}. Watching will continue.")
        return False


def _run_staged_converter_safely(
    config: PipelineConfig,
    converter: str,
    selected_input: Path | None = None,
) -> bool:
    try:
        run_staged_converter_stage(config, converter=converter, selected_input=selected_input)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\n{converter_label(converter)} converter step failed with exit code {code}. Watching will continue.")
        return False


def _run_fed_sysml_terraform_safely(config: PipelineConfig, action: str, *, auto_approve: bool) -> bool:
    try:
        run_fed_sysml_terraform_stage(config, action=action, auto_approve=auto_approve)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nfed-sysml {action} workflow failed with exit code {code}. Watching will continue.")
        return False


def _run_fed_sysml_terraform_plan_safely(config: PipelineConfig, *, save_plan: bool) -> bool:
    try:
        run_fed_sysml_terraform_plan_stage(config, save_plan=save_plan)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nfed-sysml Terraform plan failed with exit code {code}. Watching will continue.")
        return False


def _run_fed_sysml_terraform_apply_saved_plan_safely(config: PipelineConfig) -> bool:
    try:
        run_fed_sysml_terraform_apply_saved_plan_stage(config)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nfed-sysml apply/configuration failed with exit code {code}. Watching will continue.")
        return False


def _run_cloud_deployer_test_simulator_safely(config: PipelineConfig, deployment_name: str) -> bool:
    try:
        start_cloud_deployer_test_simulator_stage(config, deployment_name)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\ncloud-deployer-test-simulator failed with exit code {code}. Watching will continue.")
        return False


def _remove_cloud_deployer_test_simulator_safely(config: PipelineConfig, deployment_name: str | None = None) -> bool:
    try:
        if deployment_name is None:
            remove_all_cloud_deployer_test_simulators_stage(config)
        else:
            remove_cloud_deployer_test_simulator_stage(config, deployment_name)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\ncloud-deployer-test-simulator cleanup failed with exit code {code}.")
        return False


def _run_local_grafana_safely(config: PipelineConfig) -> bool:
    try:
        start_local_grafana_stage(config)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nLocal Grafana failed with exit code {code}. Watching will continue.")
        return False


def _stop_local_grafana_safely(config: PipelineConfig) -> bool:
    try:
        stop_local_grafana_stage(config)
        return True
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        print(f"\nLocal Grafana cleanup failed with exit code {code}. Watching will continue.")
        return False


def _prompt_yes_no(user_input: UserInput, prompt: str) -> bool:
    print(prompt, end="", flush=True)
    while True:
        line = user_input.get_line(timeout=None)
        if line is None:
            continue
        answer = line.strip().lower()
        if _is_exit(answer):
            raise StopRequested
        if answer in ("", "n", "no"):
            return False
        if answer in ("y", "yes", "run"):
            return True
        print("Please answer 'y', 'n', or 'exit': ", end="", flush=True)


def _prompt_digital_twin_manager_action(
    user_input: UserInput,
    converter_name: str,
) -> DigitalTwinManagerAction | None:
    print(
        f"Continue after {converter_name} with digital-twin-manager "
        "[deploy/plan/apply/N]? ",
        end="",
        flush=True,
    )
    while True:
        line = user_input.get_line(timeout=None)
        if line is None:
            continue
        action = line.strip().lower()
        if _is_exit(action):
            raise StopRequested
        if action in ("", "n", "no"):
            return None
        if action in ("deploy", "plan", "apply"):
            return action
        print("Please answer 'deploy', 'plan', 'apply', 'n', or 'exit': ", end="", flush=True)


def _run_digital_twin_manager_apply_with_confirmation(
    config: PipelineConfig,
    user_input: UserInput,
    deployment_name: str,
) -> bool:
    if not _prompt_yes_no(
        user_input,
        f"Apply the saved digital-twin-manager plan for {deployment_name}? [y/N] ",
    ):
        print("Skipped digital-twin-manager apply; the saved plan remains available.")
        return False

    print(f"Applying digital-twin-manager deployment plan: {deployment_name}")
    return _run_digital_twin_manager_action_safely(config, "apply", deployment_name)


def _run_selected_digital_twin_manager_action(
    config: PipelineConfig,
    user_input: UserInput,
    action: DigitalTwinManagerAction,
    deployment_name: str,
) -> bool:
    if action == "apply":
        return _run_digital_twin_manager_apply_with_confirmation(
            config,
            user_input,
            deployment_name,
        )

    action_message = {
        "deploy": "Deploying digital-twin-manager input",
        "plan": "Planning digital-twin-manager deployment changes",
    }[action]
    print(f"{action_message}: {deployment_name}")
    return _run_digital_twin_manager_action_safely(
        config,
        action,
        deployment_name=deployment_name,
    )


def _continue_pipeline_after_converter(
    config: PipelineConfig,
    user_input: UserInput,
    converter_name: str,
) -> None:
    action = _prompt_digital_twin_manager_action(user_input, converter_name)
    if action is None:
        print("Stopped before digital-twin-manager.")
        return

    deployment_name = read_manager_input_twin_name()
    manager_succeeded = _run_selected_digital_twin_manager_action(
        config,
        user_input,
        action,
        deployment_name,
    )
    if not manager_succeeded:
        return

    if action == "plan":
        if not _run_digital_twin_manager_apply_with_confirmation(
            config,
            user_input,
            deployment_name,
        ):
            return
        action = "apply"

    if _prompt_yes_no(
        user_input,
        f"Run federation workflow after digital twin manager {action}? [y/N] ",
    ):
        _run_federation_safely(config)


def _select_manager_deployment(user_input: UserInput, requested_name: str | None) -> str | None:
    deployments = list_manager_deployments()
    if not deployments:
        print(
            "No saved digital-twin-manager deployments found. "
            "Run the pipeline first so deployment input is saved."
        )
        return None

    if requested_name:
        resolved = _resolve_manager_deployment_selection(requested_name, deployments)
        if resolved:
            return resolved
        _print_unknown_deployment(requested_name, deployments)
        return None

    print("\nSaved digital-twin-manager deployments:")
    for index, deployment_name in enumerate(deployments, start=1):
        print(f"{index}. {deployment_name}")

    print("Select digital twin deployment by number or name [exit to cancel]: ", end="", flush=True)
    while True:
        line = user_input.get_line(timeout=None)
        if line is None:
            continue
        answer = line.strip()
        if _is_exit(answer.lower()):
            raise StopRequested
        if not answer:
            print("Please enter a deployment number, name, or 'exit': ", end="", flush=True)
            continue

        resolved = _resolve_manager_deployment_selection(answer, deployments)
        if resolved:
            return resolved

        _print_unknown_deployment(answer, deployments, prefix="Please choose an available deployment")
        print("Selection: ", end="", flush=True)


def _select_running_simulator(user_input: UserInput, requested_name: str | None) -> str | None:
    states = list_simulator_states()
    deployments = [str(state["digital_twin_name"]) for state in states]
    if not deployments:
        print("No running cloud-deployer-test-simulator instances found.")
        return None

    if requested_name:
        resolved = _resolve_manager_deployment_selection(requested_name, deployments)
        if resolved:
            return resolved
        _print_unknown_deployment(requested_name, deployments, prefix="Unknown running simulator")
        return None

    print("\nRunning cloud-deployer-test-simulator instances:")
    for index, state in enumerate(states, start=1):
        print(f"{index}. {state['digital_twin_name']} ({state['url']})")

    print("Select simulator by number or digital twin name [exit to cancel]: ", end="", flush=True)
    while True:
        line = user_input.get_line(timeout=None)
        if line is None:
            continue
        answer = line.strip()
        if _is_exit(answer.lower()):
            raise StopRequested
        if not answer:
            print("Please enter a simulator number, digital twin name, or 'exit': ", end="", flush=True)
            continue

        resolved = _resolve_manager_deployment_selection(answer, deployments)
        if resolved:
            return resolved

        _print_unknown_deployment(answer, deployments, prefix="Please choose a running simulator")
        print("Selection: ", end="", flush=True)


def _select_staged_sysml_v2_input(user_input: UserInput, requested_file: str | None) -> Path | None:
    sources = list_staged_converter_inputs("v2")
    if not sources:
        print("No staged sysml-v2 .sysml inputs found in pipeline/digital-twin-profile-sysml-v2/input.")
        return None

    if requested_file:
        resolved = _resolve_staged_file_selection(requested_file, sources)
        if resolved:
            return resolved
        _print_unknown_staged_file(requested_file, sources)
        return None

    if len(sources) == 1:
        print(f"Using staged sysml-v2 input: {relative_to_repo(sources[0])}")
        return sources[0]

    print("\nStaged sysml-v2 inputs:")
    for index, source in enumerate(sources, start=1):
        print(f"{index}. {source.name}")

    print("Select sysml-v2 input by number or file name [exit to cancel]: ", end="", flush=True)
    while True:
        line = user_input.get_line(timeout=None)
        if line is None:
            continue
        answer = line.strip()
        if _is_exit(answer.lower()):
            raise StopRequested
        if not answer:
            print("Please enter an input number, file name, or 'exit': ", end="", flush=True)
            continue

        resolved = _resolve_staged_file_selection(answer, sources)
        if resolved:
            return resolved

        _print_unknown_staged_file(answer, sources, prefix="Please choose an available sysml-v2 input")
        print("Selection: ", end="", flush=True)


def _resolve_manager_deployment_selection(selection: str, deployments: list[str]) -> str | None:
    if selection.isdigit():
        index = int(selection)
        if 1 <= index <= len(deployments):
            return deployments[index - 1]
        return None

    exact = [name for name in deployments if name == selection]
    if len(exact) == 1:
        return exact[0]

    folded = [name for name in deployments if name.casefold() == selection.casefold()]
    if len(folded) == 1:
        return folded[0]
    return None


def _resolve_staged_file_selection(selection: str, sources: list[Path]) -> Path | None:
    if selection.isdigit():
        index = int(selection)
        if 1 <= index <= len(sources):
            return sources[index - 1]
        return None

    exact = [
        source
        for source in sources
        if source.name == selection or str(source) == selection or relative_to_repo(source) == selection
    ]
    if len(exact) == 1:
        return exact[0]

    folded_selection = selection.casefold()
    folded = [
        source
        for source in sources
        if source.name.casefold() == folded_selection
        or str(source).casefold() == folded_selection
        or relative_to_repo(source).casefold() == folded_selection
    ]
    if len(folded) == 1:
        return folded[0]
    return None


def _print_unknown_deployment(selection: str, deployments: list[str], *, prefix: str = "Unknown digital twin deployment") -> None:
    available = ", ".join(deployments)
    print(f"{prefix} '{selection}'. Available deployments: {available}")


def _print_unknown_staged_file(
    selection: str,
    sources: list[Path],
    *,
    prefix: str = "Unknown staged sysml-v2 input",
) -> None:
    available = ", ".join(source.name for source in sources)
    print(f"{prefix} '{selection}'. Available inputs: {available}")


def _handle_command(config: PipelineConfig, command: str, user_input: UserInput) -> None:
    command_text = command.strip()
    value = command_text.lower()
    if not value:
        return
    if _is_exit(value):
        raise StopRequested
    if handle_evaluation_command(config, command_text):
        return
    if value in ("fed prepare", "fed configure"):
        try:
            if value == "fed prepare":
                prepare_federation_hooks()
            else:
                configure_federation_hooks()
        except SystemExit:
            print(f"\n{value} did not complete. Watching will continue.")
        return
    fed_terraform_action = _fed_sysml_terraform_action(value)
    if fed_terraform_action:
        if fed_terraform_action == "plan":
            print("Planning fed-sysml Terraform output.")
            _run_fed_sysml_terraform_safely(config, fed_terraform_action, auto_approve=False)
            return
        if fed_terraform_action == "apply":
            print("Planning fed-sysml Terraform output for apply.")
            if not _run_fed_sysml_terraform_plan_safely(config, save_plan=True):
                return
            if not _prompt_yes_no(user_input, "Apply this fed-sysml Terraform plan? [y/N] "):
                print("Skipped fed-sysml Terraform apply.")
                return
            print("Applying saved fed-sysml Terraform plan.")
            _run_fed_sysml_terraform_apply_saved_plan_safely(config)
            return
        if not _prompt_yes_no(user_input, "Destroy fed-sysml Terraform resources? [y/N] "):
            print("Skipped fed-sysml Terraform destroy.")
            return
        print("Destroying fed-sysml Terraform resources.")
        _run_fed_sysml_terraform_safely(config, fed_terraform_action, auto_approve=True)
        return
    converter, converter_target = _sysml_profile_command_target(command_text)
    if converter:
        label = converter_label(converter)
        selected_input = None
        if converter == "v1" and converter_target:
            print(
                "SysML v1 converter commands use staged input and do not take a target/path. "
                f"Use 'continue {label}'."
            )
            return
        if converter == "v2":
            selected_input = _select_staged_sysml_v2_input(user_input, converter_target)
            if selected_input is None:
                return
        print(f"Continuing from {label} staged input.")
        converter_succeeded = _run_staged_converter_safely(config, converter, selected_input)
        if not converter_succeeded:
            return
        _continue_pipeline_after_converter(config, user_input, label)
        return
    if _is_continue_fed_sysml(value):
        print("Continuing from fed-sysml.")
        _run_federation_safely(config)
        return
    is_plan_manager, requested_deployment = _digital_twin_manager_command_target(
        command_text,
        PLAN_DIGITAL_TWIN_MANAGER_ALIASES,
    )
    if is_plan_manager:
        deployment_name = _select_manager_deployment(user_input, requested_deployment)
        if not deployment_name:
            return
        print(f"Planning digital-twin-manager deployment changes: {deployment_name}")
        plan_succeeded = _run_digital_twin_manager_action_safely(config, "plan", deployment_name)
        if not plan_succeeded:
            return
        apply_succeeded = _run_digital_twin_manager_apply_with_confirmation(
            config,
            user_input,
            deployment_name,
        )
        if apply_succeeded and _prompt_yes_no(
            user_input,
            "Run federation workflow after digital twin manager apply? [y/N] ",
        ):
            _run_federation_safely(config)
        return
    is_apply_manager, requested_deployment = _digital_twin_manager_command_target(
        command_text,
        APPLY_DIGITAL_TWIN_MANAGER_ALIASES,
    )
    if is_apply_manager:
        deployment_name = _select_manager_deployment(user_input, requested_deployment)
        if not deployment_name:
            return
        apply_succeeded = _run_digital_twin_manager_apply_with_confirmation(
            config,
            user_input,
            deployment_name,
        )
        if apply_succeeded and _prompt_yes_no(
            user_input,
            "Run federation workflow after digital twin manager apply? [y/N] ",
        ):
            _run_federation_safely(config)
        return
    is_continue_manager, requested_deployment = _digital_twin_manager_command_target(
        command_text,
        CONTINUE_DIGITAL_TWIN_MANAGER_ALIASES,
    )
    if is_continue_manager:
        deployment_name = _select_manager_deployment(user_input, requested_deployment)
        if not deployment_name:
            return
        run_federation = _prompt_yes_no(user_input, "Run federation workflow after digital twin manager? [y/N] ")
        print(f"Continuing from digital-twin-manager deployment: {deployment_name}")
        manager_succeeded = _run_digital_twin_manager_action_safely(config, "deploy", deployment_name)
        if run_federation and manager_succeeded:
            _run_federation_safely(config)
        return
    is_destroy_manager, requested_deployment = _digital_twin_manager_command_target(
        command_text,
        DESTROY_DIGITAL_TWIN_MANAGER_ALIASES,
    )
    if is_destroy_manager:
        deployment_name = _select_manager_deployment(user_input, requested_deployment)
        if not deployment_name:
            return
        if not _prompt_yes_no(user_input, "Destroy deployed digital twin resources? [y/N] "):
            print("Skipped digital-twin-manager destroy.")
            return
        print(f"Destroying digital-twin-manager deployment: {deployment_name}")
        _run_digital_twin_manager_destroy_safely(config, deployment_name)
        return
    is_start_simulator, requested_deployment = _simulator_command_target(command_text, START_SIMULATOR_ALIASES)
    if is_start_simulator:
        deployment_name = _select_manager_deployment(user_input, requested_deployment)
        if not deployment_name:
            return
        print(f"Starting cloud-deployer-test-simulator for deployment: {deployment_name}")
        _run_cloud_deployer_test_simulator_safely(config, deployment_name)
        return
    is_stop_simulator, requested_deployment = _simulator_command_target(command_text, STOP_SIMULATOR_ALIASES)
    if is_stop_simulator:
        deployment_name = _select_running_simulator(user_input, requested_deployment)
        if not deployment_name:
            return
        print(f"Stopping cloud-deployer-test-simulator for deployment: {deployment_name}")
        _remove_cloud_deployer_test_simulator_safely(config, deployment_name)
        return
    is_start_grafana, requested_target = _grafana_command_target(command_text, START_GRAFANA_ALIASES)
    if is_start_grafana:
        if requested_target:
            print("Local Grafana is shared and does not take a digital twin target. Use 'start grafana'.")
            return
        print("Starting local Grafana.")
        _run_local_grafana_safely(config)
        return
    is_stop_grafana, requested_target = _grafana_command_target(command_text, STOP_GRAFANA_ALIASES)
    if is_stop_grafana:
        if requested_target:
            print("Local Grafana is shared and does not take a digital twin target. Use 'stop grafana'.")
            return
        print("Stopping local Grafana.")
        _stop_local_grafana_safely(config)
        return

    if value in ("help", "?"):
        _print_commands()
        return
    print("Unknown command. Type 'help' for commands or 'exit' to stop.")


def _digital_twin_manager_command_target(
    command: str,
    aliases: tuple[list[str], ...],
) -> tuple[bool, str | None]:
    return _command_target(command, aliases)


def _simulator_command_target(
    command: str,
    aliases: tuple[list[str], ...],
) -> tuple[bool, str | None]:
    return _command_target(command, aliases)


def _grafana_command_target(
    command: str,
    aliases: tuple[list[str], ...],
) -> tuple[bool, str | None]:
    return _command_target(command, aliases)


def _sysml_profile_command_target(command: str) -> tuple[str | None, str | None]:
    matched, target = _command_target(command, CONTINUE_SYSML_V1_ALIASES)
    if matched:
        return "v1", target

    matched, target = _command_target(command, CONTINUE_SYSML_V2_ALIASES)
    if matched:
        return "v2", target

    return None, None


def _command_target(
    command: str,
    aliases: tuple[list[str], ...],
) -> tuple[bool, str | None]:
    raw_parts = command.split()
    expanded_tokens: list[str] = []
    raw_index_by_expanded_token: list[int] = []

    for raw_index, part in enumerate(raw_parts):
        for token in part.replace("-", " ").replace("_", " ").split():
            expanded_tokens.append(token.lower())
            raw_index_by_expanded_token.append(raw_index)

    for alias in sorted(aliases, key=len, reverse=True):
        if expanded_tokens[:len(alias)] != alias:
            continue
        if not raw_index_by_expanded_token:
            return True, None
        consumed_raw_index = raw_index_by_expanded_token[len(alias) - 1]
        target_parts = raw_parts[consumed_raw_index + 1:]
        return True, " ".join(target_parts) if target_parts else None

    return False, None


def _is_exit(value: str) -> bool:
    return value in ("exit", "quit", "q")


def _is_continue_fed_sysml(value: str) -> bool:
    tokens = value.replace("-", " ").replace("_", " ").split()
    return tokens in (
        ["fed", "sysml"],
        ["federation"],
        ["continue", "fed", "sysml"],
        ["continue", "with", "fed", "sysml"],
        ["continue", "federation"],
        ["continue", "with", "federation"],
    )


def _fed_sysml_terraform_action(value: str) -> str | None:
    tokens = value.replace("-", " ").replace("_", " ").split()
    aliases = {
        "plan": (
            ["fed", "terraform", "plan"],
            ["fed", "sysml", "terraform", "plan"],
            ["federation", "terraform", "plan"],
        ),
        "apply": (
            ["fed", "terraform", "apply"],
            ["fed", "sysml", "terraform", "apply"],
            ["federation", "terraform", "apply"],
        ),
        "destroy": (
            ["fed", "terraform", "destroy"],
            ["fed", "sysml", "terraform", "destroy"],
            ["federation", "terraform", "destroy"],
        ),
    }
    for action, candidates in aliases.items():
        if tokens in candidates:
            return action
    return None


def _is_continue_digital_twin_manager(value: str) -> bool:
    matched, _ = _digital_twin_manager_command_target(value, CONTINUE_DIGITAL_TWIN_MANAGER_ALIASES)
    return matched


def _is_plan_digital_twin_manager(value: str) -> bool:
    matched, _ = _digital_twin_manager_command_target(value, PLAN_DIGITAL_TWIN_MANAGER_ALIASES)
    return matched


def _is_apply_digital_twin_manager(value: str) -> bool:
    matched, _ = _digital_twin_manager_command_target(value, APPLY_DIGITAL_TWIN_MANAGER_ALIASES)
    return matched


def _is_destroy_digital_twin_manager(value: str) -> bool:
    matched, _ = _digital_twin_manager_command_target(value, DESTROY_DIGITAL_TWIN_MANAGER_ALIASES)
    return matched


def _is_continue_sysml_profile(value: str) -> bool:
    converter, target = _sysml_profile_command_target(value)
    return converter is not None and target is None


def _is_start_cloud_deployer_test_simulator(value: str) -> bool:
    matched, _ = _simulator_command_target(value, START_SIMULATOR_ALIASES)
    return matched


def _is_stop_cloud_deployer_test_simulator(value: str) -> bool:
    matched, _ = _simulator_command_target(value, STOP_SIMULATOR_ALIASES)
    return matched


def _is_start_local_grafana(value: str) -> bool:
    matched, target = _grafana_command_target(value, START_GRAFANA_ALIASES)
    return matched and target is None


def _is_stop_local_grafana(value: str) -> bool:
    matched, target = _grafana_command_target(value, STOP_GRAFANA_ALIASES)
    return matched and target is None


def _print_commands() -> None:
    print("Available commands:")
    print("- continue sysml-v1              Run staged digital-twin-profile-sysml-v1 input.")
    print("- continue sysml-v2 [file]       Run one staged digital-twin-profile-sysml-v2 input.")
    print("- continue digital-twin-manager [name]  Deploy a saved digital-twin-manager input.")
    print("- plan digital-twin-manager [name]      Plan changes to a saved digital-twin-manager deployment.")
    print("- apply digital-twin-manager [name]     Apply its saved digital-twin-manager plan.")
    print("- destroy digital-twin-manager [name]   Destroy a saved digital-twin-manager deployment.")
    print("- continue fed-sysml  Resume from the fed-sysml step using staged manager output.")
    print("- fed prepare        Resolve federation targets locally; may run before the last twin is deployed.")
    print("- fed configure      Retry configuration after a successful federation Terraform apply.")
    print("- fed terraform plan  Run Terraform init and plan for generated fed-sysml output.")
    print("- fed terraform apply  Run Terraform init, plan, and apply for generated fed-sysml output.")
    print("- fed terraform destroy  Destroy fed-sysml Terraform resources.")
    print("- start simulator [name]  Start cloud-deployer-test-simulator for a saved digital twin.")
    print("- stop simulator [name]   Stop and remove a running cloud-deployer-test-simulator.")
    print("- start grafana           Start local Grafana with generated provisioning.")
    print("- stop grafana            Stop and remove local Grafana.")
    print("- plan evaluation <type> <twin> [config]  Inspect an evaluation without AWS calls.")
    print("- evaluate <type> <twin> [config]         Run an evaluation against a saved deployment.")
    print("- exit                Stop the watcher.")


def _print_infrastructure_ready() -> None:
    print("\nInfrastructure is up:")
    print("- enterprise-architect: http://127.0.0.1:6080")
    print("- sysml-kernel: service sysml-kernel / container sysml-kernel-container")
