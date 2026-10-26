from __future__ import annotations

from pathlib import Path

from .command_runner import run_command
from .errors import fail
from .pipeline_paths import FEDERATION_TERRAFORM_PLAN_FILE, PROFILE_SERVICES, relative_to_repo

INFRASTRUCTURE_SERVICES = ("enterprise-architect", "sysml-kernel")
SIMULATOR_SERVICE = "cloud-deployer-test-simulator"
LOCAL_GRAFANA_SERVICE = "local-grafana"


def compose_command(
    compose_file: Path,
    profiles: tuple[str, ...] = (),
    *,
    project_name: str | None = None,
) -> list[str]:
    command = ["docker", "compose"]
    if project_name:
        command.extend(["--project-name", project_name])
    command.extend(["-f", str(compose_file)])
    for profile in profiles:
        command.extend(["--profile", profile])
    return command


def with_profiles(profiles: tuple[str, ...], *extra_profiles: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*profiles, *extra_profiles)))


def run_digital_twin_evaluation(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    action: str,
    evaluation_type: str,
    deployment_dir: Path,
    evaluation_config: Path,
    output_dir: Path,
    show_container_logs: bool,
) -> None:
    command = compose_command(compose_file, with_profiles(profiles, "evaluation")) + [
        "run", "--rm", "--build", "--no-deps", "-T", "digital-twin-evaluation",
        action, evaluation_type,
        "--deployment", "/evaluation/deployment", "--config", "/evaluation/config.json",
    ]
    if action == "run":
        command.extend(["--output", "/evaluation/results"])
    run_command(command, show_output=show_container_logs, env={
        "EVALUATION_DEPLOYMENT_HOST_DIR": deployment_dir.resolve().as_posix(),
        "EVALUATION_CONFIG_HOST_FILE": evaluation_config.resolve().as_posix(),
        "EVALUATION_OUTPUT_HOST_DIR": output_dir.resolve().as_posix(),
    })


def start_infrastructure(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    print("\nStarting infrastructure services:")
    for service in INFRASTRUCTURE_SERVICES:
        print(f"- {service}")
    print(f"Docker Compose file: {relative_to_repo(compose_file)}")

    command = compose_command(compose_file, profiles) + ["up", "-d"]
    if build_images:
        command.append("--build")
    command.extend(INFRASTRUCTURE_SERVICES)
    run_command(command, show_output=show_container_logs)


def remove_infrastructure(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    show_container_logs: bool,
) -> None:
    print("\nRemoving infrastructure containers:")
    for service in INFRASTRUCTURE_SERVICES:
        print(f"- {service}")

    command = compose_command(compose_file, profiles) + [
        "rm",
        "--force",
        "--stop",
        *INFRASTRUCTURE_SERVICES,
    ]
    run_command(command, show_output=show_container_logs)


def run_converter(
    converter: str,
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    container_input_file: str | None,
    digital_twin_name: str,
    path_maps: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
    input_host_dir: Path | None = None,
) -> None:
    service = PROFILE_SERVICES[converter]
    command = compose_command(compose_file, profiles) + ["run", "--rm", "-T"]
    if build_images:
        command.append("--build")
    if path_maps:
        command.extend(["-e", "DTP_PATH_MAP=" + ";".join(path_maps)])
    command.append(service)

    if converter == "v1":
        if not container_input_file:
            fail("Internal error: missing SysML v1 input file.")
        command.extend([container_input_file, digital_twin_name])

    env = None
    if input_host_dir:
        env = {"DTP_V2_INPUT_HOST_DIR": input_host_dir.resolve().as_posix()}

    run_command(command, show_output=show_container_logs, env=env)


def run_manager_deploy(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    run_manager_action(
        "deploy",
        compose_file=compose_file,
        profiles=profiles,
        build_images=build_images,
        show_container_logs=show_container_logs,
    )


def run_manager_plan(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    run_manager_action(
        "plan",
        compose_file=compose_file,
        profiles=profiles,
        build_images=build_images,
        show_container_logs=show_container_logs,
    )


def run_manager_apply(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    run_manager_action(
        "apply",
        compose_file=compose_file,
        profiles=profiles,
        build_images=build_images,
        show_container_logs=show_container_logs,
    )


def run_manager_destroy(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    run_manager_action(
        "destroy",
        compose_file=compose_file,
        profiles=profiles,
        build_images=build_images,
        show_container_logs=show_container_logs,
    )


def run_manager_action(
    action: str,
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    command = compose_command(compose_file, profiles) + ["run", "--rm", "-T"]
    if build_images:
        command.append("--build")
    command.append("digital-twin-manager")
    run_command(command, stdin=f"{action}\nexit\n", show_output=show_container_logs)


def run_fed_sysml(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    command = compose_command(compose_file, profiles) + ["run", "--rm", "-T"]
    if build_images:
        command.append("--build")
    command.append("fed-sysml")
    run_command(command, show_output=show_container_logs)


def run_fed_sysml_terraform_init(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    run_fed_sysml_terraform(
        ["init", "-input=false"],
        compose_file=compose_file,
        profiles=profiles,
        build_images=build_images,
        show_container_logs=show_container_logs,
    )


def run_fed_sysml_terraform_plan(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
    save_plan: bool,
) -> None:
    args = ["plan", "-input=false"]
    if save_plan:
        args.append(f"-out={FEDERATION_TERRAFORM_PLAN_FILE}")
    run_fed_sysml_terraform(
        args,
        compose_file=compose_file,
        profiles=profiles,
        build_images=build_images,
        show_container_logs=show_container_logs,
    )


def run_fed_sysml_terraform_apply_plan(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    run_fed_sysml_terraform(
        ["apply", "-input=false", FEDERATION_TERRAFORM_PLAN_FILE],
        compose_file=compose_file,
        profiles=profiles,
        build_images=build_images,
        show_container_logs=show_container_logs,
    )


def run_fed_sysml_terraform_destroy(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
    auto_approve: bool,
) -> None:
    args = ["destroy", "-input=false"]
    if auto_approve:
        args.append("-auto-approve")
    run_fed_sysml_terraform(
        args,
        compose_file=compose_file,
        profiles=profiles,
        build_images=build_images,
        show_container_logs=show_container_logs,
    )


def run_fed_sysml_terraform(
    terraform_args: list[str],
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    build_images: bool,
    show_container_logs: bool,
) -> None:
    command = compose_command(compose_file, profiles) + [
        "run",
        "--rm",
        "-T",
        "--entrypoint",
        "terraform",
    ]
    if build_images:
        command.append("--build")
    command.extend(["fed-sysml", "-chdir=/pipeline/output", *terraform_args])
    run_command(command, show_output=show_container_logs)


def start_cloud_deployer_test_simulator(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    project_name: str,
    input_dir: Path,
    host_port: int,
    build_images: bool,
    show_container_logs: bool,
) -> None:
    command = compose_command(
        compose_file,
        with_profiles(profiles, "simulator"),
        project_name=project_name,
    ) + ["up", "-d"]
    if build_images:
        command.append("--build")
    command.append(SIMULATOR_SERVICE)
    run_command(
        command,
        show_output=show_container_logs,
        env={
            "SIMULATOR_INPUT_HOST_DIR": input_dir.resolve().as_posix(),
            "SIMULATOR_HOST_PORT": str(host_port),
        },
    )


def remove_cloud_deployer_test_simulator(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    project_name: str,
    show_container_logs: bool,
) -> None:
    print("\nRemoving cloud-deployer-test-simulator container:")
    print(f"- {SIMULATOR_SERVICE} ({project_name})")

    command = compose_command(
        compose_file,
        with_profiles(profiles, "simulator"),
        project_name=project_name,
    ) + [
        "rm",
        "--force",
        "--stop",
        SIMULATOR_SERVICE,
    ]
    run_command(command, show_output=show_container_logs)


def start_local_grafana(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    project_name: str,
    host_port: int,
    build_images: bool,
    show_container_logs: bool,
) -> None:
    command = compose_command(
        compose_file,
        with_profiles(profiles, "grafana"),
        project_name=project_name,
    ) + ["up", "-d"]
    if build_images:
        command.append("--build")
    command.append(LOCAL_GRAFANA_SERVICE)
    run_command(
        command,
        show_output=show_container_logs,
        env={"LOCAL_GRAFANA_HOST_PORT": str(host_port)},
    )


def remove_local_grafana(
    *,
    compose_file: Path,
    profiles: tuple[str, ...],
    project_name: str,
    show_container_logs: bool,
) -> None:
    print("\nRemoving local Grafana container:")
    print(f"- {LOCAL_GRAFANA_SERVICE} ({project_name})")

    command = compose_command(
        compose_file,
        with_profiles(profiles, "grafana"),
        project_name=project_name,
    ) + [
        "rm",
        "--force",
        "--stop",
        LOCAL_GRAFANA_SERVICE,
    ]
    run_command(command, show_output=show_container_logs)
