"""Strategy-specific preparation and configuration around fed-sysml/Terraform.

Only registered strategy names select helpers. The generated manifest binds those
helpers to the deployment inputs and Terraform output that were actually built.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .command_runner import run_command
from .errors import fail
from .pipeline_paths import FEDERATION_INPUT_DIR, FEDERATION_OUTPUT_DIR, REPO_ROOT

MANIFEST_NAME = "federation-hooks.json"


@dataclass(frozen=True)
class FederationHooks:
    dependencies: tuple[str, ...]
    before_generate: str | None = None
    after_apply: str | None = None


def _deployment_files(*twins: str) -> tuple[str, ...]:
    return tuple(
        f"pipeline/digital-twin-manager/deployments/{twin}/{part}"
        for twin in twins
        for part in (
            "input/config_iot_devices.json",
            "input/config_hierarchy.json",
            f"output/{twin}_federation_input.json",
        )
    )


_BATTERY_DEVICES = (
    "pipeline/digital-twin-manager/deployments/dtcBattery/input/config_iot_devices.json",
)

# Demo-specific knowledge belongs here, not in pipeline command dispatch.
HOOKS = {
    "dtc-GridBatteryPushStrategy": FederationHooks(
        _BATTERY_DEVICES, before_generate="resolve_grid_battery_push_target.py",
    ),
    "dtc-GridBatteryMaxPowerStrategy": FederationHooks(
        _BATTERY_DEVICES, before_generate="resolve_grid_battery_maxpower_target.py",
    ),
    "dtc-PVBatteryGeneratedPowerStrategy": FederationHooks(
        _BATTERY_DEVICES, before_generate="resolve_pv_battery_generatedpower_target.py",
    ),
    "dtc-ChargerBatteryPlugStrategy": FederationHooks(
        _BATTERY_DEVICES, before_generate="resolve_charger_battery_plug_target.py",
    ),
    "dtc-PVWeatherStrategy": FederationHooks(
        _deployment_files("dtcWeather", "dtcPV"), after_apply="federate_pv_weather.py",
    ),
    "dtc-BatteryChargerDecisionStrategy": FederationHooks(
        _deployment_files("dtcGrid", "dtcBattery", "dtcCharger"),
        after_apply="federate_battery_charger_decision.py",
    ),
}


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(f"Cannot read {path.name}: {error}")
    if not isinstance(data, dict):
        fail(f"Expected a JSON object in {path}.")
    return data


def selected_strategies() -> list[str]:
    """Select only registered newStrategies, preserving configuration order."""
    data = _load_json(FEDERATION_INPUT_DIR / "fedtwin.json")
    selected: list[str] = []
    try:
        groups = data["fedTwins"]
        if not isinstance(groups, list):
            raise ValueError("fedTwins must be a list")
        for group in groups:
            strategies = group["newStrategies"]
            if not isinstance(strategies, list):
                raise ValueError("newStrategies must be a list")
            for strategy in strategies:
                name = strategy["name"]
                if not isinstance(name, str) or not name:
                    raise ValueError("each strategy must have a nonempty name")
                if name in HOOKS and name not in selected:
                    selected.append(name)
    except (KeyError, TypeError, ValueError) as error:
        fail(f"Invalid federation hook selection in fedtwin.json: {error}")
    return selected


def _script_environment() -> dict[str, str]:
    # Match Compose precedence: the process environment overrides .env values.
    try:
        from dotenv import dotenv_values
    except ImportError:
        fail("Federation helpers require python-dotenv. Run 'uv sync' before starting the pipeline.")

    return {
        key: value for key, value in dotenv_values(REPO_ROOT / ".env").items()
        if value is not None and key not in os.environ
    }


def _run_helper(script: str, *, check: bool = False) -> None:
    path = REPO_ROOT / "scripts" / script
    if not path.is_file():
        fail(f"Missing federation helper: {path}")
    command = [sys.executable, str(path)]
    if check:
        command.append("--check")
    try:
        run_command(command, env=_script_environment())
    except SystemExit:
        fail(f"Federation helper {script} failed. See its output above.")


def _fingerprints(paths: list[Path]) -> dict[str, str]:
    result = {}
    for path in paths:
        if not path.is_file():
            fail(f"Missing federation input: {path}. Deploy the required twin first.")
        result[path.relative_to(REPO_ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def prepare_federation_hooks(*, for_generation: bool = False) -> dict:
    """Run resolvers; full generation also validates post-apply dependencies.

    `fed prepare` deliberately needs only the resolver inputs (Battery), so it
    can run before Charger exists. Full generation checks all selected helpers.
    """
    selected = selected_strategies()
    inputs = [FEDERATION_INPUT_DIR / "fedtwin.json"]
    for name in selected:
        hook = HOOKS[name]
        if for_generation or hook.before_generate:
            inputs.extend(REPO_ROOT / path for path in hook.dependencies)
    if for_generation:
        inputs.append(FEDERATION_INPUT_DIR / "brokerConfig.json")
    fingerprints = _fingerprints(inputs)
    if for_generation and any(HOOKS[name].after_apply for name in selected):
        if importlib.util.find_spec("boto3") is None:
            fail("Federation configuration requires boto3. Run 'uv sync' before starting the pipeline.")
        for name in selected:
            if script := HOOKS[name].after_apply:
                _run_helper(script, check=True)
    for name in selected:
        if script := HOOKS[name].before_generate:
            _run_helper(script)
    print("Federation preparation complete.")
    return {
        "version": 1,
        "strategies": selected,
        "inputs": fingerprints,
        "artifacts": {},
        "terraform_applied": False,
        "configured": False,
    }


def invalidate_federation_hooks() -> None:
    (FEDERATION_OUTPUT_DIR / MANIFEST_NAME).unlink(missing_ok=True)


def _generated_artifacts() -> list[Path]:
    return [
        *FEDERATION_OUTPUT_DIR.glob("*.tf"),
        *(FEDERATION_OUTPUT_DIR / ".build").rglob("*.py"),
    ]


def save_federation_hooks(manifest: dict, staged_inputs: list[Path]) -> None:
    # The staged federation inputs cover trigger twins as well as hook targets.
    paths = _generated_artifacts()
    paths.extend(staged_inputs)
    for staged in staged_inputs:
        twin = staged.name.removesuffix("_federation_input.json")
        source = REPO_ROOT / "pipeline/digital-twin-manager/deployments" / twin / "output" / staged.name
        fingerprints = _fingerprints([source])
        if source.read_bytes() != staged.read_bytes() or any(
            key in manifest["inputs"] and manifest["inputs"][key] != value
            for key, value in fingerprints.items()
        ):
            fail(f"Deployment changed during federation generation: {twin}. Run 'continue fed-sysml' again.")
        manifest["inputs"].update(fingerprints)
    if not (FEDERATION_OUTPUT_DIR / "main.tf").is_file():
        fail("fed-sysml did not generate main.tf; federation hooks were not saved.")
    manifest["artifacts"] = _fingerprints(paths)
    _write_manifest(manifest)
    validate_federation_hooks()


def _write_manifest(manifest: dict) -> None:
    path = FEDERATION_OUTPUT_DIR / MANIFEST_NAME
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _generated_strategies() -> set[str]:
    main = FEDERATION_OUTPUT_DIR / "main.tf"
    source = main.read_text(encoding="utf-8") if main.is_file() else ""
    return set(re.findall(r'resource\s+"aws_lambda_function"\s+"([^"]+)_pipeline"', source)) & HOOKS.keys()


def validate_federation_hooks() -> dict | None:
    """Reject stale inputs before plan/apply, without touching AWS."""
    path = FEDERATION_OUTPUT_DIR / MANIFEST_NAME
    generated = _generated_strategies()
    if not path.is_file():
        if generated:
            fail("Federation hook manifest is missing. Run 'continue fed-sysml' before plan/apply.")
        return None  # Older, unrelated federations need no microgrid helpers.
    manifest = _load_json(path)
    selected = manifest.get("strategies")
    if (
        manifest.get("version") != 1
        or not isinstance(selected, list)
        or not all(isinstance(name, str) and name in HOOKS for name in selected)
        or len(set(selected)) != len(selected)
        or set(selected) != generated
        or not isinstance(manifest.get("terraform_applied"), bool)
        or not isinstance(manifest.get("configured"), bool)
    ):
        fail("Federation hook manifest does not match generated resources. Run 'continue fed-sysml'.")
    for section in ("inputs", "artifacts"):
        fingerprints = manifest.get(section)
        if not isinstance(fingerprints, dict) or not fingerprints:
            fail("Federation hook fingerprints are missing. Run 'continue fed-sysml'.")
        for relative, digest in fingerprints.items():
            if not isinstance(relative, str) or not isinstance(digest, str):
                fail("Invalid federation hook fingerprint. Run 'continue fed-sysml'.")
            source = (REPO_ROOT / relative).resolve()
            if not source.is_relative_to(REPO_ROOT.resolve()):
                fail("Invalid federation hook input path. Run 'continue fed-sysml'.")
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                fail(f"Federation input/output changed: {relative}. Run 'continue fed-sysml', then plan/apply again.")
    if any(path.relative_to(REPO_ROOT).as_posix() not in manifest["artifacts"] for path in _generated_artifacts()):
        fail("Generated federation files were added. Run 'continue fed-sysml', then plan/apply again.")
    return manifest


def mark_federation_applied(manifest: dict | None, *, applied: bool) -> None:
    if manifest is not None:
        manifest["terraform_applied"] = applied
        manifest["configured"] = False
        _write_manifest(manifest)


def configure_federation_hooks() -> None:
    manifest = validate_federation_hooks()
    if manifest is None or not manifest["strategies"]:
        print("No federation configuration hooks are registered for this output.")
        return
    if not manifest["terraform_applied"]:
        fail("Run 'fed terraform apply' successfully before 'fed configure'.")
    manifest["configured"] = False
    _write_manifest(manifest)
    try:
        for name in manifest["strategies"]:
            if script := HOOKS[name].after_apply:
                _run_helper(script)
    except SystemExit:
        fail("Terraform was applied, but federation configuration is incomplete. Fix the error and retry 'fed configure'.")
    manifest["configured"] = True
    _write_manifest(manifest)
    print("Federation configuration complete.")
