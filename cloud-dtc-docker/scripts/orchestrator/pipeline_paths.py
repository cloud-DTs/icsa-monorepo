from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_FILE = REPO_ROOT / "orchestrator_config.json"
PIPELINE_ROOT = REPO_ROOT / "pipeline"

CONFIG_FILES = (
    "config.json",
    "config_hierarchy.json",
    "config_iot_devices.json",
    "config_events.json",
)

SIMULATOR_CONFIG_FILES = (
    "config.json",
    "config_hierarchy.json",
    "config_iot_devices.json",
)

PROFILE_SERVICES = {
    "v1": "digital-twin-profile-sysml-v1",
    "v2": "digital-twin-profile-sysml-v2",
}

PROFILE_INPUT_DIRS = {
    "v1": PIPELINE_ROOT / "digital-twin-profile-sysml-v1" / "input",
    "v2": PIPELINE_ROOT / "digital-twin-profile-sysml-v2" / "input",
}

PROFILE_OUTPUT_DIRS = {
    "v1": PIPELINE_ROOT / "digital-twin-profile-sysml-v1" / "output",
    "v2": PIPELINE_ROOT / "digital-twin-profile-sysml-v2" / "output",
}

MANAGER_INPUT_DIR = PIPELINE_ROOT / "digital-twin-manager" / "input"
MANAGER_OUTPUT_DIR = PIPELINE_ROOT / "digital-twin-manager" / "output"
MANAGER_DEPLOYMENTS_DIR = PIPELINE_ROOT / "digital-twin-manager" / "deployments"

FEDERATION_INPUT_DIR = PIPELINE_ROOT / "fed-sysml" / "input"
FEDERATION_OUTPUT_DIR = PIPELINE_ROOT / "fed-sysml" / "output"
FEDERATION_TERRAFORM_MAIN_FILE = FEDERATION_OUTPUT_DIR / "main.tf"
FEDERATION_TERRAFORM_PLAN_FILE = "fed-sysml.tfplan"
FEDERATION_TERRAFORM_PLAN_PATH = FEDERATION_OUTPUT_DIR / FEDERATION_TERRAFORM_PLAN_FILE

GRAFANA_DIR = PIPELINE_ROOT / "grafana"
GRAFANA_STATE_PATH = GRAFANA_DIR / "grafana.json"

def converter_label(converter: str) -> str:
    return "sysml-v1" if converter == "v1" else "sysml-v2"


def resolve_repo_path(path: Path | str) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def relative_to_repo(path: Path | str) -> str:
    path = Path(path)
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
