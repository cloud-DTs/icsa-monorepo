from __future__ import annotations

from pathlib import Path

from .config import PipelineConfig
from .federation_hooks import (
    configure_federation_hooks,
    invalidate_federation_hooks,
    mark_federation_applied,
    prepare_federation_hooks,
    save_federation_hooks,
    validate_federation_hooks,
)
from .docker_compose import (
    remove_cloud_deployer_test_simulator,
    remove_local_grafana,
    run_converter,
    run_manager_apply,
    run_manager_destroy,
    run_manager_deploy,
    run_manager_plan,
    run_fed_sysml,
    run_fed_sysml_terraform_apply_plan,
    run_fed_sysml_terraform_destroy,
    run_fed_sysml_terraform_init,
    run_fed_sysml_terraform_plan,
    start_cloud_deployer_test_simulator,
    start_local_grafana,
)
from .pipeline_paths import (
    FEDERATION_OUTPUT_DIR,
    FEDERATION_TERRAFORM_MAIN_FILE,
    FEDERATION_TERRAFORM_PLAN_PATH,
    MANAGER_INPUT_DIR,
    MANAGER_OUTPUT_DIR,
    SIMULATOR_CONFIG_FILES,
    converter_label,
    relative_to_repo,
    resolve_repo_path,
)
from .errors import fail
from .staging import (
    allocate_simulator_host_port,
    clean_pipeline_dir,
    copy_configs_to_manager,
    delete_simulator_state,
    delete_local_grafana_state,
    find_converter_output,
    has_config_set,
    invalidate_manager_deployment_plan,
    list_simulator_states,
    local_grafana_project_name,
    prepare_manager_stage,
    prepare_federation_stage,
    prepare_local_grafana_stage,
    print_file_listing,
    print_config_set,
    print_manager_outputs,
    print_text_files,
    read_existing_manager_credentials,
    read_existing_manager_providers,
    read_local_grafana_state,
    read_simulator_state,
    require_manager_deployment_simulator_input,
    require_manager_redeployment_state,
    restore_manager_deployment_input,
    restore_manager_deployment_output,
    save_manager_deployment_input,
    save_manager_deployment_output,
    save_manager_deployment_plan,
    select_staged_converter_input,
    simulator_project_name,
    stage_converter_input,
    stage_federation_inputs_from_deployments,
    write_simulator_state,
)


def run_pipeline(config: PipelineConfig, *, source: Path, converter: str) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")
    if config.run_federation_workflow and not config.deploy_to_aws:
        fail("run_federation_workflow requires deploy_to_aws=true because fed-sysml uses digital-twin-manager deploy output.")

    source = resolve_repo_path(source)

    print(f"\nConverter: {converter_label(converter)}")
    print(f"Docker Compose file: {relative_to_repo(compose_file)}")
    print(f"Enterprise Architect export: {relative_to_repo(source)}")

    container_input_file, used_model_files, input_host_dir = stage_converter_input(
        converter,
        source,
        clean_stage=config.clean_stage,
    )
    print_file_listing("used model file(s)", used_model_files)
    if converter == "v2":
        print_text_files("sysml-v2 input", used_model_files)

    run_converter(
        converter,
        compose_file=compose_file,
        profiles=config.compose_profiles,
        container_input_file=container_input_file,
        digital_twin_name=config.digital_twin_name,
        path_maps=config.path_maps,
        build_images=config.build_images,
        show_container_logs=config.show_container_logs,
        input_host_dir=input_host_dir,
    )

    generated_twin_dir = config.generated_twin_dir
    if not generated_twin_dir and converter == "v1":
        generated_twin_dir = config.digital_twin_name.lower()

    converter_output = find_converter_output(
        converter,
        generated_twin_dir=generated_twin_dir,
    )
    if config.show_output_configs:
        print_config_set("converter output", converter_output)

    stage_digital_twin_manager_input(config, converter_output)

    if not config.deploy_to_aws:
        print("\nStopped before AWS deploy. Manager configs are ready in " + relative_to_repo(MANAGER_INPUT_DIR))
        return

    run_digital_twin_manager_deploy_stage(config)

    if not config.run_federation_workflow:
        print("\nStopped before federation workflow. Manager output is ready in " + relative_to_repo(MANAGER_OUTPUT_DIR))
        return

    run_federation_stage(config)


def run_staged_converter_stage(config: PipelineConfig, *, converter: str, selected_input: Path | None = None) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    print(f"\nConverter: {converter_label(converter)}")
    print(f"Docker Compose file: {relative_to_repo(compose_file)}")

    container_input_file, used_model_files, input_host_dir = select_staged_converter_input(
        converter,
        clean_output=config.clean_stage,
        selected_input=selected_input,
    )
    print_file_listing(f"staged {converter_label(converter)} input", used_model_files)
    if converter == "v2":
        print_text_files("sysml-v2 input", used_model_files)

    run_converter(
        converter,
        compose_file=compose_file,
        profiles=config.compose_profiles,
        container_input_file=container_input_file,
        digital_twin_name=config.digital_twin_name,
        path_maps=config.path_maps,
        build_images=config.build_images,
        show_container_logs=config.show_container_logs,
        input_host_dir=input_host_dir,
    )

    generated_twin_dir = config.generated_twin_dir
    if not generated_twin_dir and converter == "v1":
        generated_twin_dir = config.digital_twin_name.lower()

    converter_output = find_converter_output(
        converter,
        generated_twin_dir=generated_twin_dir,
    )
    if config.show_output_configs:
        print_config_set("converter output", converter_output)

    stage_digital_twin_manager_input(config, converter_output)
    print("\nConverter completed. Manager configs are ready in " + relative_to_repo(MANAGER_INPUT_DIR))


def stage_digital_twin_manager_input(config: PipelineConfig, converter_output: Path) -> None:
    saved_credentials = None
    if not config.aws_credentials_file:
        saved_credentials = read_existing_manager_credentials()
    saved_providers = read_existing_manager_providers()

    prepare_manager_stage(
        clean_stage=config.clean_stage,
        keep_credentials=saved_credentials,
        keep_providers=saved_providers,
    )
    copy_configs_to_manager(converter_output, config.aws_credentials_file)
    save_manager_deployment_input()

    if config.show_configs:
        print_config_set("digital-twin-manager input", MANAGER_INPUT_DIR)


def run_digital_twin_manager_deploy_stage(config: PipelineConfig, deployment_name: str | None = None) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    if deployment_name:
        restore_manager_deployment_input(deployment_name)

    _require_manager_input()
    clean_pipeline_dir(MANAGER_OUTPUT_DIR)

    run_manager_deploy(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        build_images=config.build_images,
        show_container_logs=config.show_container_logs,
    )
    save_manager_deployment_output()
    print_manager_outputs()


def run_digital_twin_manager_plan_stage(config: PipelineConfig, deployment_name: str | None = None) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    if deployment_name:
        restore_manager_deployment_input(deployment_name)
        restore_manager_deployment_output(deployment_name)

    _require_manager_input()
    require_manager_redeployment_state()
    invalidate_manager_deployment_plan(deployment_name)

    run_manager_plan(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        build_images=config.build_images,
        show_container_logs=config.show_container_logs,
    )
    save_manager_deployment_plan()


def run_digital_twin_manager_apply_stage(config: PipelineConfig, deployment_name: str | None = None) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    if deployment_name:
        restore_manager_deployment_input(deployment_name)
        restore_manager_deployment_output(deployment_name, require_plan=True)

    _require_manager_input()
    require_manager_redeployment_state(require_plan=True)

    try:
        run_manager_apply(
            compose_file=compose_file,
            profiles=config.compose_profiles,
            build_images=config.build_images,
            show_container_logs=config.show_container_logs,
        )
    except SystemExit:
        save_manager_deployment_plan()
        raise

    save_manager_deployment_output()
    print_manager_outputs()


def run_digital_twin_manager_destroy_stage(config: PipelineConfig, deployment_name: str | None = None) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    if deployment_name:
        restore_manager_deployment_input(deployment_name)

    _require_manager_input()

    run_manager_destroy(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        build_images=config.build_images,
        show_container_logs=config.show_container_logs,
    )


def _require_manager_input() -> None:
    if not has_config_set(MANAGER_INPUT_DIR):
        fail(
            "digital-twin-manager input is missing or incomplete. "
            f"Run the pipeline first so configs are staged in {relative_to_repo(MANAGER_INPUT_DIR)}."
        )


def start_cloud_deployer_test_simulator_stage(config: PipelineConfig, deployment_name: str) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    input_dir = require_manager_deployment_simulator_input(deployment_name)
    simulator_inputs = [input_dir / file_name for file_name in SIMULATOR_CONFIG_FILES]
    state = read_simulator_state(deployment_name)
    if state:
        project_name = str(state["project_name"])
        host_port = int(state["host_port"])
    else:
        project_name = simulator_project_name(deployment_name)
        host_port = allocate_simulator_host_port()

    print_file_listing("cloud-deployer-test-simulator input", simulator_inputs)
    start_cloud_deployer_test_simulator(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        project_name=project_name,
        input_dir=input_dir,
        host_port=host_port,
        build_images=config.build_images,
        show_container_logs=config.show_container_logs,
    )
    state = write_simulator_state(
        deployment_name,
        project_name=project_name,
        host_port=host_port,
        input_dir=input_dir,
    )
    print(f"\ncloud-deployer-test-simulator for {state['digital_twin_name']} is running at {state['url']}")


def remove_cloud_deployer_test_simulator_stage(config: PipelineConfig, deployment_name: str) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    state = read_simulator_state(deployment_name)
    project_name = str(state["project_name"]) if state else simulator_project_name(deployment_name)
    remove_cloud_deployer_test_simulator(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        project_name=project_name,
        show_container_logs=config.show_container_logs,
    )
    delete_simulator_state(deployment_name)


def remove_all_cloud_deployer_test_simulators_stage(config: PipelineConfig) -> None:
    states = list_simulator_states()
    if not states:
        return

    for state in states:
        remove_cloud_deployer_test_simulator_stage(config, str(state["digital_twin_name"]))


def start_local_grafana_stage(config: PipelineConfig) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    state = prepare_local_grafana_stage()
    start_local_grafana(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        project_name=str(state["project_name"]),
        host_port=int(state["host_port"]),
        build_images=config.build_images,
        show_container_logs=config.show_container_logs,
    )
    print(f"\nLocal Grafana is running at {state['url']}")


def stop_local_grafana_stage(config: PipelineConfig) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    state = read_local_grafana_state()
    project_name = str(state["project_name"]) if state else local_grafana_project_name()
    remove_local_grafana(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        project_name=project_name,
        show_container_logs=config.show_container_logs,
    )
    delete_local_grafana_state()


def run_federation_stage(config: PipelineConfig) -> None:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")

    hook_manifest = prepare_federation_hooks(for_generation=True)
    prepare_federation_stage(clean_stage=config.clean_stage)
    invalidate_federation_hooks()
    _remove_stale_fed_sysml_plan()
    federation_inputs = stage_federation_inputs_from_deployments()
    print_file_listing("fed-sysml strategy input(s)", federation_inputs)

    run_fed_sysml(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        build_images=config.build_images,
        show_container_logs=config.show_container_logs,
    )
    save_federation_hooks(hook_manifest, federation_inputs)

    if config.fed_sysml_terraform_action != "none":
        run_fed_sysml_terraform_stage(config)

    print_file_listing("fed-sysml output", sorted(FEDERATION_OUTPUT_DIR.glob("*")))


def run_fed_sysml_terraform_stage(
    config: PipelineConfig,
    *,
    action: str | None = None,
    auto_approve: bool | None = None,
) -> None:
    action = action or config.fed_sysml_terraform_action
    if action == "none":
        return
    if action not in ("plan", "apply", "destroy"):
        fail(f"Unknown fed-sysml Terraform action: {action}")

    effective_auto_approve = config.fed_sysml_terraform_auto_approve if auto_approve is None else auto_approve
    if action in ("apply", "destroy") and not effective_auto_approve:
        fail(
            f"fed-sysml Terraform action '{action}' requires "
            "fed_sysml_terraform_auto_approve=true or manual watcher confirmation."
        )

    if action == "plan":
        run_fed_sysml_terraform_plan_stage(config, save_plan=False)
        return

    if action == "apply":
        run_fed_sysml_terraform_plan_stage(config, save_plan=True)
        run_fed_sysml_terraform_apply_saved_plan_stage(config)
        return

    compose_file = _require_fed_sysml_terraform_ready(config)
    print("\nRunning fed-sysml Terraform destroy")
    invalidate_federation_hooks()
    run_fed_sysml_terraform_destroy(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        build_images=config.build_images,
        show_container_logs=True,
        auto_approve=effective_auto_approve,
    )


def run_fed_sysml_terraform_plan_stage(config: PipelineConfig, *, save_plan: bool) -> None:
    compose_file = _require_fed_sysml_terraform_ready(config)
    validate_federation_hooks()
    print("\nRunning fed-sysml Terraform plan")
    run_fed_sysml_terraform_init(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        build_images=config.build_images,
        show_container_logs=True,
    )
    _remove_stale_fed_sysml_plan()
    run_fed_sysml_terraform_plan(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        build_images=config.build_images,
        show_container_logs=True,
        save_plan=save_plan,
    )


def run_fed_sysml_terraform_apply_saved_plan_stage(config: PipelineConfig) -> None:
    compose_file = _require_fed_sysml_terraform_ready(config)
    if not FEDERATION_TERRAFORM_PLAN_PATH.is_file():
        fail(
            "fed-sysml Terraform saved plan is missing. "
            f"Expected {relative_to_repo(FEDERATION_TERRAFORM_PLAN_PATH)}."
        )

    hook_manifest = validate_federation_hooks()
    mark_federation_applied(hook_manifest, applied=False)
    print("\nApplying saved fed-sysml Terraform plan")
    run_fed_sysml_terraform_apply_plan(
        compose_file=compose_file,
        profiles=config.compose_profiles,
        build_images=config.build_images,
        show_container_logs=True,
    )

    mark_federation_applied(hook_manifest, applied=True)
    configure_federation_hooks()


def _require_fed_sysml_terraform_ready(config: PipelineConfig) -> Path:
    compose_file = resolve_repo_path(config.compose_file)
    if not compose_file.is_file():
        fail(f"Docker Compose file does not exist: {relative_to_repo(compose_file)}")
    if not FEDERATION_TERRAFORM_MAIN_FILE.is_file():
        fail(
            "fed-sysml Terraform output is missing. "
            f"Expected {relative_to_repo(FEDERATION_TERRAFORM_MAIN_FILE)}. "
            "Run 'continue fed-sysml' first."
        )
    return compose_file


def _remove_stale_fed_sysml_plan() -> None:
    if FEDERATION_TERRAFORM_PLAN_PATH.exists():
        if FEDERATION_TERRAFORM_PLAN_PATH.is_dir():
            fail(f"Expected Terraform plan file but found directory: {relative_to_repo(FEDERATION_TERRAFORM_PLAN_PATH)}")
        FEDERATION_TERRAFORM_PLAN_PATH.unlink()
        print(f"Removed stale Terraform plan: {relative_to_repo(FEDERATION_TERRAFORM_PLAN_PATH)}")
