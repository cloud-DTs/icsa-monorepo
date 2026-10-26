from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex

from .config import PipelineConfig
from .docker_compose import run_digital_twin_evaluation
from .errors import fail
from .pipeline_paths import (
    MANAGER_DEPLOYMENTS_DIR, PIPELINE_ROOT, relative_to_repo, resolve_repo_path,
)
from .staging import resolve_manager_deployment_name


EVALUATION_INPUT_DIR = PIPELINE_ROOT / "digital-twin-evaluation" / "input"
EVALUATION_OUTPUT_DIR = PIPELINE_ROOT / "digital-twin-evaluation" / "output"
USAGE = "Use 'evaluate <type> <twin> [config]' or 'plan evaluation <type> <twin> [config]'."


@dataclass(frozen=True)
class EvaluationRequest:
    action: str
    evaluation_type: str
    twin_name: str
    config_file: Path | None


def parse_evaluation_command(command: str) -> EvaluationRequest | None:
    if not re.match(r"^(evaluate|plan\s+evaluation)(?:\s|$)", command.strip(), re.IGNORECASE):
        return None
    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""  # Preserve Windows path separators while supporting quoted paths.
    parts = list(lexer)
    action = "run" if parts[0].lower() == "evaluate" else "plan"
    args = parts[1:] if action == "run" else parts[2:]
    if len(args) not in (2, 3) or not re.fullmatch(r"[a-z][a-z0-9_-]*", args[0]):
        raise ValueError(USAGE)
    return EvaluationRequest(action, args[0], args[1], Path(args[2]) if len(args) == 3 else None)


def handle_evaluation_command(config: PipelineConfig, command: str) -> bool:
    try:
        request = parse_evaluation_command(command)
        if request is None:
            return False
        run_evaluation_stage(config, request)
    except (ValueError, SystemExit) as error:
        print(f"\nEvaluation did not complete: {error}. Watching will continue.")
    return True


def run_evaluation_stage(config: PipelineConfig, request: EvaluationRequest) -> None:
    twin = resolve_manager_deployment_name(request.twin_name)
    deployment_dir = MANAGER_DEPLOYMENTS_DIR / twin
    state = deployment_dir / "output" / ".digital-twin-manager-state"
    required = [state / "metadata.json", *(
        state / "configs" / name
        for name in ("config.json", "config_hierarchy.json", "config_iot_devices.json")
    )]
    if any(not path.is_file() for path in required):
        fail(f"Applied deployment state for '{twin}' is incomplete. Complete deploy or init-state first.")
    try:
        metadata = json.loads((state / "metadata.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        fail(f"Cannot read applied deployment metadata: {error}")
    if not isinstance(metadata, dict) or metadata.get("digitalTwinName") != twin:
        fail(f"The saved state belongs to a different twin than '{twin}'. Complete its deploy first.")
    config_file = (
        resolve_repo_path(request.config_file) if request.config_file
        else EVALUATION_INPUT_DIR / f"{twin}.{request.evaluation_type}.json"
    )
    if not config_file.is_file():
        fail(f"Evaluation config is missing: {relative_to_repo(config_file)}. Supply a config file explicitly.")
    EVALUATION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nEvaluation {request.action}: {request.evaluation_type} / {twin}")
    run_digital_twin_evaluation(
        compose_file=resolve_repo_path(config.compose_file), profiles=config.compose_profiles,
        action=request.action, evaluation_type=request.evaluation_type,
        deployment_dir=deployment_dir, evaluation_config=config_file,
        output_dir=EVALUATION_OUTPUT_DIR, show_container_logs=config.show_container_logs,
    )
    if request.action == "run":
        print(f"Evaluation reports: {relative_to_repo(EVALUATION_OUTPUT_DIR / twin)}")
