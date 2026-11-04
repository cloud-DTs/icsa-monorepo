from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
from datetime import datetime
from pathlib import Path
from typing import Callable

from .errors import fail
from .pipeline_paths import (
    CONFIG_FILES,
    GRAFANA_DIR,
    GRAFANA_STATE_PATH,
    MANAGER_DEPLOYMENTS_DIR,
    MANAGER_INPUT_DIR,
    MANAGER_OUTPUT_DIR,
    PIPELINE_ROOT,
    PROFILE_INPUT_DIRS,
    PROFILE_OUTPUT_DIRS,
    SIMULATOR_CONFIG_FILES,
    FEDERATION_INPUT_DIR,
    FEDERATION_OUTPUT_DIR,
    relative_to_repo,
    resolve_repo_path,
)
from .xmi_validation import validate_sysml_v1_export

FEDERATION_TERRAFORM_STATE_ENTRIES = {
    ".terraform",
    ".terraform.lock.hcl",
    "terraform.tfstate",
    "terraform.tfstate.backup",
}
MANAGER_STATE_DIR_NAME = ".digital-twin-manager-state"
MANAGER_STATE_CONFIG_DIR_NAME = "configs"
MANAGER_STATE_METADATA_FILE_NAME = "metadata.json"
MANAGER_STATE_PLAN_FILE_NAME = "plan.json"
SIMULATOR_STATE_FILE = "simulator.json"
SIMULATOR_PORT_START = 5000
SIMULATOR_PORT_END = 5999
SimulatorState = dict[str, str | int]
GrafanaState = dict[str, str | int]
GRAFANA_DEFAULT_HOST_PORT = 3000
GRAFANA_PROJECT_NAME = "cloud-dtc-grafana"
GRAFANA_SERVICE_URL = "http://127.0.0.1"


def clean_pipeline_dir(path: Path) -> None:
    path = _safe_pipeline_child(path)
    if path.exists() and not path.is_dir():
        fail(f"Expected directory but found file: {path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def stage_converter_input(
    converter: str, source: Path, *, clean_stage: bool
) -> tuple[str | None, list[Path], Path | None]:
    input_dir = PROFILE_INPUT_DIRS[converter]
    output_dir = PROFILE_OUTPUT_DIRS[converter]

    if converter == "v1":
        if clean_stage:
            clean_pipeline_dir(input_dir)
        else:
            ensure_dir(input_dir)
        container_input_file, staged_files = _stage_sysml_v1_input(source, input_dir)
        input_host_dir = None
    else:
        staged_files = _select_sysml_v2_inputs(source)
        input_host_dir = _prepare_sysml_v2_run_input(input_dir, staged_files)
        container_input_file = None

    if clean_stage:
        clean_pipeline_dir(output_dir)
    else:
        ensure_dir(output_dir)
    return container_input_file, staged_files, input_host_dir


def list_staged_converter_inputs(converter: str) -> list[Path]:
    input_dir = PROFILE_INPUT_DIRS[converter]
    ensure_dir(input_dir)
    if converter == "v1":
        return _files_with_suffixes(input_dir, ".xmi", ".xml")
    return _files_with_suffixes(input_dir, ".sysml")


def select_staged_converter_input(
    converter: str,
    *,
    clean_output: bool,
    selected_input: Path | None = None,
) -> tuple[str | None, list[Path], Path | None]:
    input_dir = PROFILE_INPUT_DIRS[converter]
    output_dir = PROFILE_OUTPUT_DIRS[converter]

    ensure_dir(input_dir)
    if clean_output:
        clean_pipeline_dir(output_dir)
    else:
        ensure_dir(output_dir)

    if converter == "v1":
        source = _select_staged_sysml_v1_input(input_dir)
        validate_sysml_v1_export(source)
        return f"/pipeline/input/{source.name}", [source], None

    sources = _select_staged_sysml_v2_inputs(input_dir)
    if selected_input is None:
        return None, sources, None

    source = _resolve_staged_sysml_v2_input(input_dir, selected_input, sources)
    run_input_dir = _prepare_sysml_v2_run_input(input_dir, [source])
    return None, [source], run_input_dir


def find_converter_output(converter: str, *, generated_twin_dir: str | None) -> Path:
    output_root = PROFILE_OUTPUT_DIRS[converter]

    if generated_twin_dir:
        expected_dir = output_root / generated_twin_dir
        if has_config_set(expected_dir):
            return expected_dir
        fail(f"Expected converter output directory is missing or incomplete: {relative_to_repo(expected_dir)}")

    candidates = set()
    if has_config_set(output_root):
        candidates.add(output_root)

    for config_json in output_root.rglob("config.json"):
        candidate = config_json.parent
        if has_config_set(candidate):
            candidates.add(candidate)

    if not candidates:
        fail(f"No complete config set found under {relative_to_repo(output_root)}")

    sorted_candidates = sorted(candidates, key=_latest_config_mtime, reverse=True)
    if len(sorted_candidates) > 1:
        print(f"Multiple converter outputs found. Using newest: {relative_to_repo(sorted_candidates[0])}")
    return sorted_candidates[0]


def prepare_manager_stage(
    *,
    clean_stage: bool,
    keep_credentials: bytes | None,
    keep_providers: bytes | None,
) -> None:
    if clean_stage:
        clean_pipeline_dir(MANAGER_INPUT_DIR)
        clean_pipeline_dir(MANAGER_OUTPUT_DIR)
    else:
        ensure_dir(MANAGER_INPUT_DIR)
        ensure_dir(MANAGER_OUTPUT_DIR)

    if keep_credentials is not None:
        (MANAGER_INPUT_DIR / "config_credentials.json").write_bytes(keep_credentials)

    if keep_providers is not None:
        (MANAGER_INPUT_DIR / "config_providers.json").write_bytes(keep_providers)


def prepare_federation_stage(*, clean_stage: bool) -> None:
    strategy_input_dir = FEDERATION_INPUT_DIR / "strategyInputs"
    if clean_stage:
        ensure_dir(FEDERATION_INPUT_DIR)
        clean_pipeline_dir(strategy_input_dir)
        clean_federation_output_dir()
    else:
        ensure_dir(FEDERATION_INPUT_DIR)
        ensure_dir(strategy_input_dir)
        ensure_dir(FEDERATION_OUTPUT_DIR)


def clean_federation_output_dir() -> None:
    path = _safe_pipeline_child(FEDERATION_OUTPUT_DIR)
    if path.exists() and not path.is_dir():
        fail(f"Expected directory but found file: {path}")
    path.mkdir(parents=True, exist_ok=True)

    for child in path.iterdir():
        if child.name in FEDERATION_TERRAFORM_STATE_ENTRIES:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def read_existing_manager_credentials() -> bytes | None:
    credentials = MANAGER_INPUT_DIR / "config_credentials.json"
    if credentials.is_file():
        return credentials.read_bytes()
    return None


def read_existing_manager_providers() -> bytes | None:
    providers = MANAGER_INPUT_DIR / "config_providers.json"
    if providers.is_file():
        return providers.read_bytes()
    return None


def copy_configs_to_manager(converter_output_dir: Path, aws_credentials_file: Path | None) -> None:
    for file_name in CONFIG_FILES:
        source = converter_output_dir / file_name
        target = MANAGER_INPUT_DIR / file_name
        shutil.copy2(source, target)
        print(f"Copied {relative_to_repo(source)} -> {relative_to_repo(target)}")

    if aws_credentials_file:
        credentials = resolve_repo_path(aws_credentials_file)
        if not credentials.is_file():
            fail(f"Credentials file does not exist: {relative_to_repo(credentials)}")
        target = MANAGER_INPUT_DIR / "config_credentials.json"
        shutil.copy2(credentials, target)
        print(f"Copied AWS credentials to {relative_to_repo(target)}")


def read_manager_input_twin_name() -> str:
    return _read_twin_name_from_config(MANAGER_INPUT_DIR / "config.json")


def list_manager_deployments() -> list[str]:
    if not MANAGER_DEPLOYMENTS_DIR.is_dir():
        return []

    deployments: list[str] = []
    for deployment_dir in MANAGER_DEPLOYMENTS_DIR.iterdir():
        input_dir = deployment_dir / "input"
        if deployment_dir.is_dir() and has_config_set(input_dir):
            deployments.append(deployment_dir.name)
    return sorted(deployments, key=str.casefold)


def save_manager_deployment_input() -> Path:
    if not has_config_set(MANAGER_INPUT_DIR):
        fail(
            "digital-twin-manager input is missing or incomplete. "
            f"Expected configs in {relative_to_repo(MANAGER_INPUT_DIR)}."
        )

    twin_name = read_manager_input_twin_name()
    target_dir = MANAGER_DEPLOYMENTS_DIR / twin_name / "input"
    _copy_directory_contents_clean(MANAGER_INPUT_DIR, target_dir)
    print(f"Saved digital-twin-manager deployment input: {relative_to_repo(target_dir)}")
    return target_dir


def save_manager_deployment_output() -> Path:
    twin_name = read_manager_input_twin_name()
    federation_input = MANAGER_OUTPUT_DIR / f"{twin_name}_federation_input.json"
    if not federation_input.is_file():
        fail(
            "digital-twin-manager federation artifact is missing. "
            f"Expected {relative_to_repo(federation_input)}."
        )

    target_dir = _save_manager_output_snapshot(twin_name)
    saved_federation_input = target_dir / federation_input.name
    print(f"Saved digital-twin-manager deployment output: {relative_to_repo(saved_federation_input)}")
    return saved_federation_input


def save_manager_deployment_plan() -> Path:
    twin_name = read_manager_input_twin_name()
    require_manager_redeployment_state(require_plan=True)
    target_dir = _save_manager_output_snapshot(twin_name)
    saved_plan = target_dir / MANAGER_STATE_DIR_NAME / MANAGER_STATE_PLAN_FILE_NAME
    print(f"Saved digital-twin-manager deployment plan: {relative_to_repo(saved_plan)}")
    return saved_plan


def invalidate_manager_deployment_plan(twin_name: str | None = None) -> None:
    plan_paths = [MANAGER_OUTPUT_DIR / MANAGER_STATE_DIR_NAME / MANAGER_STATE_PLAN_FILE_NAME]
    if twin_name:
        deployment_name = resolve_manager_deployment_name(twin_name)
        plan_paths.append(
            MANAGER_DEPLOYMENTS_DIR
            / deployment_name
            / "output"
            / MANAGER_STATE_DIR_NAME
            / MANAGER_STATE_PLAN_FILE_NAME
        )

    for plan_path in plan_paths:
        if plan_path.is_file():
            plan_path.unlink()
            print(f"Invalidated previous digital-twin-manager plan: {relative_to_repo(plan_path)}")


def _save_manager_output_snapshot(twin_name: str) -> Path:
    target_dir = MANAGER_DEPLOYMENTS_DIR / twin_name / "output"
    expected_federation_input_name = f"{twin_name}_federation_input.json"

    def skip_stale_federation_input(path: Path) -> bool:
        return path.name.endswith("_federation_input.json") and path.name != expected_federation_input_name

    _copy_directory_contents_clean(MANAGER_OUTPUT_DIR, target_dir, skip=skip_stale_federation_input)
    return target_dir


def save_manager_deployment_artifact() -> Path:
    return save_manager_deployment_output()


def restore_manager_deployment_input(twin_name: str) -> Path:
    deployment_name = resolve_manager_deployment_name(twin_name)
    source_dir = MANAGER_DEPLOYMENTS_DIR / deployment_name / "input"
    if not has_config_set(source_dir):
        fail(
            f"Saved deployment input for twin '{deployment_name}' is missing or incomplete. "
            f"Expected configs in {relative_to_repo(source_dir)}."
        )

    _copy_directory_contents_clean(source_dir, MANAGER_INPUT_DIR)
    print(f"Restored digital-twin-manager input from deployment: {relative_to_repo(source_dir)}")
    return MANAGER_INPUT_DIR


def restore_manager_deployment_output(twin_name: str, *, require_plan: bool = False) -> Path:
    deployment_name = resolve_manager_deployment_name(twin_name)
    source_dir = MANAGER_DEPLOYMENTS_DIR / deployment_name / "output"
    _require_manager_redeployment_state(
        source_dir,
        deployment_name,
        require_plan=require_plan,
    )

    _copy_directory_contents_clean(source_dir, MANAGER_OUTPUT_DIR)
    print(f"Restored digital-twin-manager output from deployment: {relative_to_repo(source_dir)}")
    return MANAGER_OUTPUT_DIR


def require_manager_redeployment_state(*, require_plan: bool = False) -> Path:
    twin_name = read_manager_input_twin_name()
    return _require_manager_redeployment_state(
        MANAGER_OUTPUT_DIR,
        twin_name,
        require_plan=require_plan,
    )


def _require_manager_redeployment_state(
    output_dir: Path,
    twin_name: str,
    *,
    require_plan: bool,
) -> Path:
    state_dir = output_dir / MANAGER_STATE_DIR_NAME
    state_config_dir = state_dir / MANAGER_STATE_CONFIG_DIR_NAME
    required_state_paths = [
        state_dir / MANAGER_STATE_METADATA_FILE_NAME,
        *(state_config_dir / file_name for file_name in CONFIG_FILES),
    ]
    missing_state_paths = [path for path in required_state_paths if not path.is_file()]
    if missing_state_paths:
        missing = ", ".join(relative_to_repo(path) for path in missing_state_paths)
        fail(
            f"digital-twin-manager redeployment state for twin '{twin_name}' is missing or incomplete. "
            f"Missing: {missing}. Use digital-twin-manager 'init-state' for existing AWS resources, "
            "or complete a fresh deploy before running plan/apply."
        )

    metadata_path = state_dir / MANAGER_STATE_METADATA_FILE_NAME
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"digital-twin-manager state metadata is not valid JSON: {relative_to_repo(metadata_path)} ({error})")
    if not isinstance(metadata, dict) or metadata.get("digitalTwinName") != twin_name:
        fail(
            f"digital-twin-manager state under {relative_to_repo(output_dir)} does not belong to twin '{twin_name}'."
        )

    plan_path = state_dir / MANAGER_STATE_PLAN_FILE_NAME
    if require_plan and not plan_path.is_file():
        fail(
            f"Saved digital-twin-manager plan for twin '{twin_name}' is missing. "
            f"Expected {relative_to_repo(plan_path)}. Run 'plan digital-twin-manager {twin_name}' first."
        )
    if require_plan:
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            fail(f"Saved digital-twin-manager plan is not valid JSON: {relative_to_repo(plan_path)} ({error})")
        if not isinstance(plan, list) or not plan:
            fail(
                f"Saved digital-twin-manager plan for twin '{twin_name}' is empty or invalid. "
                f"Run 'plan digital-twin-manager {twin_name}' again."
            )

    return state_dir


def resolve_manager_deployment_name(twin_name: str) -> str:
    if not twin_name:
        fail("Digital twin deployment name must be a non-empty string.")
    if "/" in twin_name or "\\" in twin_name:
        fail(f"Digital twin deployment name must not contain path separators: {twin_name}")

    deployments = list_manager_deployments()
    if twin_name in deployments:
        return twin_name

    matches = [name for name in deployments if name.casefold() == twin_name.casefold()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(matches)
        fail(f"Digital twin deployment name '{twin_name}' is ambiguous. Matches: {names}")

    available = ", ".join(deployments) or "(none)"
    fail(f"Unknown digital twin deployment '{twin_name}'. Available deployments: {available}")


def require_manager_deployment_simulator_input(twin_name: str) -> Path:
    deployment_name = resolve_manager_deployment_name(twin_name)
    input_dir = MANAGER_DEPLOYMENTS_DIR / deployment_name / "input"
    missing_inputs = [input_dir / file_name for file_name in SIMULATOR_CONFIG_FILES if not (input_dir / file_name).is_file()]
    if missing_inputs:
        missing = ", ".join(relative_to_repo(path) for path in missing_inputs)
        fail(
            f"cloud-deployer-test-simulator input for twin '{deployment_name}' is missing or incomplete. "
            f"Expected saved deployment input in {relative_to_repo(input_dir)}. "
            f"Missing: {missing}"
        )
    return input_dir


def simulator_project_name(twin_name: str) -> str:
    if not twin_name:
        fail("Digital twin deployment name must be a non-empty string.")

    slug = _slugify(twin_name)
    digest = hashlib.sha256(twin_name.encode("utf-8")).hexdigest()[:8]
    return f"cloud-dtc-simulator-{slug}-{digest}"


def allocate_simulator_host_port(
    *,
    start: int = SIMULATOR_PORT_START,
    end: int = SIMULATOR_PORT_END,
) -> int:
    used_ports = {
        int(state["host_port"])
        for state in list_simulator_states()
        if isinstance(state.get("host_port"), int)
    }

    for port in range(start, end + 1):
        if port in used_ports:
            continue
        if _is_local_port_available(port):
            return port

    fail(f"No available simulator host port found in range {start}-{end}.")


def list_simulator_states() -> list[SimulatorState]:
    if not MANAGER_DEPLOYMENTS_DIR.is_dir():
        return []

    states: list[SimulatorState] = []
    for state_file in sorted(MANAGER_DEPLOYMENTS_DIR.glob(f"*/{SIMULATOR_STATE_FILE}")):
        states.append(_load_simulator_state(state_file))
    return sorted(states, key=lambda state: str(state["digital_twin_name"]).casefold())


def read_simulator_state(twin_name: str) -> SimulatorState | None:
    if not twin_name:
        fail("Digital twin deployment name must be a non-empty string.")

    for state in list_simulator_states():
        state_name = str(state["digital_twin_name"])
        if state_name == twin_name or state_name.casefold() == twin_name.casefold():
            return state
    return None


def write_simulator_state(
    twin_name: str,
    *,
    project_name: str,
    host_port: int,
    input_dir: Path,
) -> SimulatorState:
    deployment_name = resolve_manager_deployment_name(twin_name)
    url = f"http://127.0.0.1:{host_port}"
    state: SimulatorState = {
        "digital_twin_name": deployment_name,
        "project_name": project_name,
        "host_port": host_port,
        "url": url,
        "input_dir": relative_to_repo(input_dir),
    }

    state_file = MANAGER_DEPLOYMENTS_DIR / deployment_name / SIMULATOR_STATE_FILE
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Saved simulator state: {relative_to_repo(state_file)}")
    return state


def delete_simulator_state(twin_name: str) -> None:
    state = read_simulator_state(twin_name)
    if not state:
        return

    state_file = MANAGER_DEPLOYMENTS_DIR / str(state["digital_twin_name"]) / SIMULATOR_STATE_FILE
    if state_file.is_file():
        state_file.unlink()
        print(f"Removed simulator state: {relative_to_repo(state_file)}")


def local_grafana_project_name() -> str:
    return GRAFANA_PROJECT_NAME


def local_grafana_host_port() -> int:
    raw_port = os.environ.get("LOCAL_GRAFANA_HOST_PORT", str(GRAFANA_DEFAULT_HOST_PORT))
    try:
        port = int(raw_port)
    except ValueError:
        fail(f"LOCAL_GRAFANA_HOST_PORT must be an integer, got: {raw_port}")
    if not (1 <= port <= 65535):
        fail(f"LOCAL_GRAFANA_HOST_PORT must be between 1 and 65535, got: {raw_port}")
    return port


def local_grafana_url(host_port: int | None = None) -> str:
    return f"{GRAFANA_SERVICE_URL}:{host_port or local_grafana_host_port()}"


def prepare_local_grafana_stage() -> GrafanaState:
    ensure_dir(GRAFANA_DIR)
    return write_local_grafana_state(host_port=local_grafana_host_port())


def write_local_grafana_state(
    *,
    host_port: int,
) -> GrafanaState:
    state: GrafanaState = {
        "project_name": local_grafana_project_name(),
        "host_port": host_port,
        "url": local_grafana_url(host_port),
    }
    GRAFANA_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAFANA_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Saved local Grafana state: {relative_to_repo(GRAFANA_STATE_PATH)}")
    return state


def read_local_grafana_state() -> GrafanaState | None:
    if not GRAFANA_STATE_PATH.is_file():
        return None
    return _load_local_grafana_state(GRAFANA_STATE_PATH)


def delete_local_grafana_state() -> None:
    if GRAFANA_STATE_PATH.is_file():
        GRAFANA_STATE_PATH.unlink()
        print(f"Removed local Grafana state: {relative_to_repo(GRAFANA_STATE_PATH)}")


def required_twins_from_fedtwin(fedtwin_path: Path) -> list[str]:
    fedtwin_path = resolve_repo_path(fedtwin_path)
    if not fedtwin_path.is_file():
        fail(f"Missing fed-sysml config file: {relative_to_repo(fedtwin_path)}")

    try:
        data = json.loads(fedtwin_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"fed-sysml config is not valid JSON: {relative_to_repo(fedtwin_path)} ({error})")

    if not isinstance(data, dict):
        fail(f"fed-sysml config root must be an object: {relative_to_repo(fedtwin_path)}")

    fed_twins = data.get("fedTwins")
    if not isinstance(fed_twins, list):
        fail("fed-sysml config field 'fedTwins' must be a list.")

    required: list[str] = []
    seen: set[str] = set()
    for fed_twin_index, fed_twin in enumerate(fed_twins):
        if not isinstance(fed_twin, dict):
            fail(f"fed-sysml config field 'fedTwins[{fed_twin_index}]' must be an object.")

        new_strategies = fed_twin.get("newStrategies", [])
        if not isinstance(new_strategies, list):
            fail(f"fed-sysml config field 'fedTwins[{fed_twin_index}].newStrategies' must be a list.")

        for new_strategy_index, new_strategy in enumerate(new_strategies):
            if not isinstance(new_strategy, dict):
                fail(
                    "fed-sysml config field "
                    f"'fedTwins[{fed_twin_index}].newStrategies[{new_strategy_index}]' must be an object."
                )

            strategy_refs = new_strategy.get("strategies", [])
            if not isinstance(strategy_refs, list):
                fail(
                    "fed-sysml config field "
                    f"'fedTwins[{fed_twin_index}].newStrategies[{new_strategy_index}].strategies' must be a list."
                )

            for strategy_ref_index, strategy_ref in enumerate(strategy_refs):
                context = (
                    f"fedTwins[{fed_twin_index}].newStrategies[{new_strategy_index}]"
                    f".strategies[{strategy_ref_index}]"
                )
                if not isinstance(strategy_ref, str):
                    fail(f"fed-sysml strategy reference '{context}' must be a string in the form 'Twin.strategy'.")

                parts = strategy_ref.split(".")
                if len(parts) != 2 or not parts[0] or not parts[1]:
                    fail(
                        f"Invalid fed-sysml strategy reference '{strategy_ref}' at {context}. "
                        "Expected 'Twin.strategy'."
                    )

                twin_name = parts[0]
                if twin_name not in seen:
                    seen.add(twin_name)
                    required.append(twin_name)

    if not required:
        fail(f"No fed-sysml strategy references found in {relative_to_repo(fedtwin_path)}")
    return required


def stage_federation_inputs() -> list[Path]:
    return stage_federation_inputs_from_deployments()


def stage_federation_inputs_from_deployments() -> list[Path]:
    for file_name in ("fedtwin.json", "brokerConfig.json"):
        config_file = FEDERATION_INPUT_DIR / file_name
        if not config_file.is_file():
            fail(f"Missing fed-sysml config file: {relative_to_repo(config_file)}")

    required_twins = required_twins_from_fedtwin(FEDERATION_INPUT_DIR / "fedtwin.json")
    target_dir = FEDERATION_INPUT_DIR / "strategyInputs"
    clean_pipeline_dir(target_dir)

    staged_files: list[Path] = []
    for twin_name in required_twins:
        source = MANAGER_DEPLOYMENTS_DIR / twin_name / "output" / f"{twin_name}_federation_input.json"
        if not source.is_file():
            fail(
                f"Missing saved federation input for twin '{twin_name}'. "
                f"Expected {relative_to_repo(source)}. "
                "Deploy that digital twin first so its output artifact is saved."
            )

        target = target_dir / source.name
        shutil.copy2(source, target)
        staged_files.append(target)
        print(f"Copied {relative_to_repo(source)} -> {relative_to_repo(target)}")

    return staged_files


def _read_twin_name_from_config(config_file: Path) -> str:
    if not config_file.is_file():
        fail(f"Missing digital-twin-manager config file: {relative_to_repo(config_file)}")

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"digital-twin-manager config is not valid JSON: {relative_to_repo(config_file)} ({error})")

    if not isinstance(data, dict):
        fail(f"digital-twin-manager config root must be an object: {relative_to_repo(config_file)}")

    name = data.get("digital_twin_name")
    if not isinstance(name, str) or not name:
        fail(f"digital-twin-manager config field 'digital_twin_name' must be a non-empty string: {relative_to_repo(config_file)}")
    if "/" in name or "\\" in name:
        fail(f"digital_twin_name must not contain path separators: {name}")
    return name


def _copy_directory_contents_clean(
    source_dir: Path,
    target_dir: Path,
    *,
    skip: Callable[[Path], bool] | None = None,
) -> None:
    if not source_dir.is_dir():
        fail(f"Expected directory but found missing path or file: {relative_to_repo(source_dir)}")

    clean_pipeline_dir(target_dir)
    for source in sorted(source_dir.iterdir()):
        if skip and skip(source):
            continue

        target = target_dir / source.name
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def _load_local_grafana_state(state_file: Path) -> GrafanaState:
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"Local Grafana state is not valid JSON: {relative_to_repo(state_file)} ({error})")

    if not isinstance(data, dict):
        fail(f"Local Grafana state root must be an object: {relative_to_repo(state_file)}")

    project_name = data.get("project_name")
    host_port = data.get("host_port")
    url = data.get("url")

    if not isinstance(project_name, str) or not project_name:
        fail(f"Local Grafana state field 'project_name' must be a non-empty string: {relative_to_repo(state_file)}")
    if not isinstance(host_port, int):
        fail(f"Local Grafana state field 'host_port' must be an integer: {relative_to_repo(state_file)}")
    if not isinstance(url, str) or not url:
        fail(f"Local Grafana state field 'url' must be a non-empty string: {relative_to_repo(state_file)}")

    return {
        "project_name": project_name,
        "host_port": host_port,
        "url": url,
    }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "item"


def _load_simulator_state(state_file: Path) -> SimulatorState:
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"Simulator state is not valid JSON: {relative_to_repo(state_file)} ({error})")

    if not isinstance(data, dict):
        fail(f"Simulator state root must be an object: {relative_to_repo(state_file)}")

    digital_twin_name = data.get("digital_twin_name")
    project_name = data.get("project_name")
    host_port = data.get("host_port")
    url = data.get("url")
    input_dir = data.get("input_dir")

    if not isinstance(digital_twin_name, str) or not digital_twin_name:
        fail(f"Simulator state field 'digital_twin_name' must be a non-empty string: {relative_to_repo(state_file)}")
    if not isinstance(project_name, str) or not project_name:
        fail(f"Simulator state field 'project_name' must be a non-empty string: {relative_to_repo(state_file)}")
    if not isinstance(host_port, int):
        fail(f"Simulator state field 'host_port' must be an integer: {relative_to_repo(state_file)}")
    if not isinstance(url, str) or not url:
        fail(f"Simulator state field 'url' must be a non-empty string: {relative_to_repo(state_file)}")
    if not isinstance(input_dir, str) or not input_dir:
        fail(f"Simulator state field 'input_dir' must be a non-empty string: {relative_to_repo(state_file)}")

    return {
        "digital_twin_name": digital_twin_name,
        "project_name": project_name,
        "host_port": host_port,
        "url": url,
        "input_dir": input_dir,
    }


def _is_local_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def print_config_set(label: str, config_dir: Path) -> None:
    print(f"\n=== {label}: {relative_to_repo(config_dir)} ===")
    for file_name in CONFIG_FILES:
        path = config_dir / file_name
        print(f"\n--- {file_name} ---")
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print(path.read_text(encoding="utf-8", errors="replace"))


def print_manager_outputs() -> None:
    federation_outputs = sorted(MANAGER_OUTPUT_DIR.glob("*_federation_input.json"))
    if not federation_outputs:
        return

    print(f"\n=== digital-twin-manager output: {relative_to_repo(MANAGER_OUTPUT_DIR)} ===")
    for output in federation_outputs:
        print(f"\n--- {output.name} ---")
        print(output.read_text(encoding="utf-8", errors="replace"))


def print_file_listing(label: str, files: list[Path]) -> None:
    print(f"\n=== {label} ===")
    if not files:
        print("(no files)")
        return

    for file_path in files:
        if not file_path.exists():
            print(f"missing        -                    {relative_to_repo(file_path)}")
            continue
        if file_path.is_dir():
            print(f"dir            -                    {relative_to_repo(file_path)}")
            continue
        size = _format_size(file_path.stat().st_size)
        modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"file  {size:>10} {modified}  {relative_to_repo(file_path)}")


def print_text_files(label: str, files: list[Path]) -> None:
    print(f"\n=== {label} ===")
    if not files:
        print("(no files)")
        return

    for file_path in files:
        print(f"\n--- {relative_to_repo(file_path)} ---")
        print(file_path.read_text(encoding="utf-8", errors="replace"))


def has_config_set(path: Path) -> bool:
    return all((path / file_name).is_file() for file_name in CONFIG_FILES)


def _stage_sysml_v1_input(source: Path, input_dir: Path) -> tuple[str, list[Path]]:
    source = _select_sysml_v1_input(source)
    if not source.is_file():
        fail(f"Enterprise Architect export file does not exist: {relative_to_repo(source)}")
    validate_sysml_v1_export(source)

    target = input_dir / source.name
    shutil.copy2(source, target)
    print(f"Copied Enterprise Architect export to {relative_to_repo(target)}")
    return f"/pipeline/input/{target.name}", [source]


def _select_sysml_v1_input(source: Path) -> Path:
    if source.is_dir():
        candidates = sorted(source.glob("*.xmi")) + sorted(source.glob("*.xml"))
        if not candidates:
            fail(f"No .xmi or .xml files found in {relative_to_repo(source)}")
        if len(candidates) > 1:
            names = ", ".join(relative_to_repo(path) for path in candidates)
            fail(f"More than one .xmi/.xml file found. Export or update one file at a time. Candidates: {names}")
        return candidates[0]
    return source


def _select_sysml_v2_inputs(source: Path) -> list[Path]:
    if source.is_dir():
        sources = _files_with_suffixes(source, ".sysml")
        if not sources:
            xml_exports = _files_with_suffixes(source, ".xml", ".xmi")
            if xml_exports:
                names = ", ".join(relative_to_repo(path) for path in xml_exports)
                fail(
                    "Found Enterprise Architect XML/XMI export(s), but sysml-v2 cannot read them: "
                    f"{names}. XML/XMI exports are routed to sysml-v1; sysml-v2 needs a .sysml text file."
                )
            fail(
                f"No .sysml files found in {relative_to_repo(source)}. "
                "SysML v2 parser reads .sysml text files only."
            )
        return sources

    if not source.is_file():
        fail(f"Enterprise Architect export file does not exist: {relative_to_repo(source)}")
    if source.suffix.lower() != ".sysml":
        if source.suffix.lower() in (".xml", ".xmi"):
            fail(
                "sysml-v2 cannot read Enterprise Architect XML/XMI exports. "
                f"XML/XMI exports are routed to sysml-v1: {relative_to_repo(source)}."
            )
        fail(f"SysML v2 parser reads .sysml text files only, got: {relative_to_repo(source)}")
    return [source]


def _select_staged_sysml_v1_input(input_dir: Path) -> Path:
    candidates = _files_with_suffixes(input_dir, ".xmi", ".xml")
    if not candidates:
        sysml_sources = _files_with_suffixes(input_dir, ".sysml")
        if sysml_sources:
            names = ", ".join(relative_to_repo(path) for path in sysml_sources)
            fail(
                "Found SysML v2 staged input(s), but sysml-v1 cannot read them: "
                f"{names}. SysML v1 needs exactly one .xml or .xmi file."
            )
        fail(
            f"No .xmi or .xml files found in {relative_to_repo(input_dir)}. "
            "SysML v1 converter reads Enterprise Architect XML/XMI exports only."
        )
    if len(candidates) > 1:
        names = ", ".join(relative_to_repo(path) for path in candidates)
        fail(f"More than one .xmi/.xml file found in staged sysml-v1 input. Candidates: {names}")
    return candidates[0]


def _select_staged_sysml_v2_inputs(input_dir: Path) -> list[Path]:
    sources = _files_with_suffixes(input_dir, ".sysml")
    if sources:
        return sources

    xml_exports = _files_with_suffixes(input_dir, ".xml", ".xmi")
    if xml_exports:
        names = ", ".join(relative_to_repo(path) for path in xml_exports)
        fail(
            "Found Enterprise Architect XML/XMI staged input(s), but sysml-v2 cannot read them: "
            f"{names}. SysML v2 parser reads .sysml text files only."
        )
    fail(
        f"No .sysml files found in {relative_to_repo(input_dir)}. "
        "SysML v2 parser reads .sysml text files only."
    )


def _resolve_staged_sysml_v2_input(input_dir: Path, selected_input: Path, sources: list[Path]) -> Path:
    selected = selected_input if selected_input.is_absolute() else input_dir / selected_input
    resolved = selected.resolve()
    for source in sources:
        if source.resolve() == resolved:
            return source
    names = ", ".join(relative_to_repo(path) for path in sources) or "none"
    fail(f"Selected SysML v2 staged input is not available: {relative_to_repo(selected)}. Available: {names}")


def _prepare_sysml_v2_run_input(input_dir: Path, sources: list[Path]) -> Path:
    run_input_dir = _safe_pipeline_child(input_dir.parent / "run-input")
    if any(source.resolve().is_relative_to(run_input_dir) for source in sources):
        fail("SysML v2 source models must be outside the temporary run-input directory.")
    clean_pipeline_dir(run_input_dir)
    for source in sources:
        target = run_input_dir / source.name
        shutil.copy2(source, target)
        print(f"Prepared SysML v2 run input: {relative_to_repo(target)}")
    return run_input_dir


def _latest_config_mtime(path: Path) -> float:
    return max((path / file_name).stat().st_mtime for file_name in CONFIG_FILES)


def _files_with_suffixes(directory: Path, *suffixes: str) -> list[Path]:
    wanted = {suffix.lower() for suffix in suffixes}
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in wanted
    )


def _format_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    return f"{size} B"


def _safe_pipeline_child(path: Path) -> Path:
    resolved = path.resolve()
    pipeline_root = PIPELINE_ROOT.resolve()
    if resolved == pipeline_root:
        fail("Refusing to clean the pipeline root itself.")
    try:
        resolved.relative_to(pipeline_root)
    except ValueError:
        fail(f"Refusing to clean path outside pipeline directory: {resolved}")
    return resolved
