#!/usr/bin/env python3
"""Federation enablement step for the dtc-PVWeatherStrategy federation.

The bulk of this federation is REAL fed-sysml: the fedtwin.json entry
"dtc-PVWeatherStrategy" (references dtcPV.isCycling) makes `continue fed-sysml`
+ `fed terraform apply` generate the Event Registry trigger, the pipeline Lambda
(collector -> strategy -> feedback in one function) and its IAM role - all in
Terraform.

fed-sysml cannot wire in dtcWeather, though: Weather is passive (no
strategyAction, so it can't appear in a `strategies` list) AND the requested
hour is dynamic (the Collector fetches fixed properties). So this step supplies
the one thing fed-sysml structurally can't, targeting the FEDERATION-OWNED
Strategy Lambda (not a twin):

  - INJECT dtcWeather's hot-reader ARN + workspace/entity/component and dtcPV's
    own production device id as env vars on dtc-PVWeatherStrategy_pipeline.
  - GRANT dtc-PVWeatherStrategy_pipeline-role lambda:InvokeFunction scoped to
    dtcWeather-hot-reader only - fed-sysml already grants invoke on the hot
    readers of the twins referenced in "strategies", but dtcWeather is not one
    of them.

The fed-sysml Lambda + role names are deterministic
(<strategyName>_pipeline / <strategyName>_pipeline-role), so no discovery is
needed. This is not the main mechanism, only the Weather-side remainder that
fed-sysml cannot express.

The orchestrator runs this helper after successful federation applies when
dtc-PVWeatherStrategy is selected. `fed configure` retries configuration without
another apply. Direct execution remains available; --check validates the local
deployment inputs without contacting AWS.

    python3 scripts/federate_pv_weather.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PV_TWIN_NAME = "dtcPV"
WEATHER_TWIN_NAME = "dtcWeather"
PV_PRODUCTION_PROPERTY_NAME = "production"

STRATEGY_NAME = "dtc-PVWeatherStrategy"
# fed-sysml generates ONE Lambda per federation, "<name>_pipeline", which calls
# collector -> our strategy code -> feedback in-process. The IAM role follows the
# same base name ("<name>_pipeline-role"). The older layout had three separate
# Lambdas chained by a Step Function and used "<name>_strategy".
STRATEGY_FUNCTION_NAME = f"{STRATEGY_NAME}_pipeline"
STRATEGY_ROLE_NAME = f"{STRATEGY_NAME}_pipeline-role"
INVOKE_POLICY_NAME = "pv-weather-federation-invoke"

WEATHER_FEDERATION_INPUT_FILE = (
    REPO_ROOT / "pipeline" / "digital-twin-manager" / "deployments"
    / WEATHER_TWIN_NAME / "output" / f"{WEATHER_TWIN_NAME}_federation_input.json"
)
WEATHER_HIERARCHY_FILE = (
    REPO_ROOT / "pipeline" / "digital-twin-manager" / "deployments"
    / WEATHER_TWIN_NAME / "input" / "config_hierarchy.json"
)
WEATHER_DEVICES_FILE = (
    REPO_ROOT / "pipeline" / "digital-twin-manager" / "deployments"
    / WEATHER_TWIN_NAME / "input" / "config_iot_devices.json"
)
PV_DEVICES_FILE = (
    REPO_ROOT / "pipeline" / "digital-twin-manager" / "deployments"
    / PV_TWIN_NAME / "input" / "config_iot_devices.json"
)


# --------------------------------------------------------------------------- #
# Discovery (local, read-only)
# --------------------------------------------------------------------------- #
def discover_weather() -> dict:
    if not WEATHER_FEDERATION_INPUT_FILE.is_file():
        raise SystemExit(
            f"Missing deployed federation input: {WEATHER_FEDERATION_INPUT_FILE}. "
            f"Deploy '{WEATHER_TWIN_NAME}' independently before running federation."
        )
    if not WEATHER_HIERARCHY_FILE.is_file():
        raise SystemExit(f"Missing deployed hierarchy: {WEATHER_HIERARCHY_FILE}.")

    if not WEATHER_DEVICES_FILE.is_file():
        raise SystemExit(f"Missing deployed device list: {WEATHER_DEVICES_FILE}.")

    federation_input = json.loads(WEATHER_FEDERATION_INPUT_FILE.read_text(encoding="utf-8"))
    hierarchy = json.loads(WEATHER_HIERARCHY_FILE.read_text(encoding="utf-8"))
    devices = json.loads(WEATHER_DEVICES_FILE.read_text(encoding="utf-8"))
    if not hierarchy:
        raise SystemExit(f"Empty hierarchy in {WEATHER_HIERARCHY_FILE}.")

    entity = hierarchy[0]
    children = entity.get("children", [])

    # The forecast values live in the generated const_component, NOT necessarily
    # children[0]. Find the device that actually holds the hourNN properties, then
    # resolve its component name from the hierarchy (device id -> child name).
    forecast_device_id = None
    for device in devices:
        names = [p.get("name", "") for p in device.get("properties", [])]
        if any(n.startswith("hour") for n in names):
            forecast_device_id = device["id"]
            break
    if forecast_device_id is None:
        raise SystemExit(
            f"No device with hourNN properties found in {WEATHER_DEVICES_FILE}. "
            "The forecast consts did not materialize - ensure they are declared at "
            "the #entity level in dtcWeather.sysml (constAttributes inside a "
            "#component are dropped by the converter) and redeploy dtcWeather."
        )

    component_name = None
    for child in children:
        if child.get("iotDeviceId") == forecast_device_id:
            component_name = child.get("name")
            break
    if not component_name:
        raise SystemExit(
            f"Could not resolve the component name for device '{forecast_device_id}' "
            f"in {WEATHER_HIERARCHY_FILE}."
        )

    return {
        "region": federation_input["region"],
        "hot_reader_arn": federation_input["hot_reader_arn"],
        "workspace_id": federation_input["twinmaker_workspace_id"],
        "entity_id": entity["id"],
        "component_name": component_name,
    }


def discover_pv_production_device_id() -> str:
    if not PV_DEVICES_FILE.is_file():
        raise SystemExit(
            f"Missing deployed device list: {PV_DEVICES_FILE}. "
            f"Deploy '{PV_TWIN_NAME}' before running federation."
        )
    devices = json.loads(PV_DEVICES_FILE.read_text(encoding="utf-8"))
    for device in devices:
        for prop in device.get("properties", []):
            if prop.get("name") == PV_PRODUCTION_PROPERTY_NAME:
                return device["id"]
    raise SystemExit(
        f"No device with property '{PV_PRODUCTION_PROPERTY_NAME}' found in {PV_DEVICES_FILE}."
    )


def discover_pv_max_power() -> str:
    """maxPower is a static constant. Read its initValue from PV's deployed
    config (the generated const_component), NOT from the runtime Collector -
    consts aren't collectible, and reading the config initValue works regardless
    of whether the const value was seeded into the store.
    """
    if not PV_DEVICES_FILE.is_file():
        raise SystemExit(
            f"Missing deployed device list: {PV_DEVICES_FILE}. "
            f"Deploy '{PV_TWIN_NAME}' before running federation."
        )
    devices = json.loads(PV_DEVICES_FILE.read_text(encoding="utf-8"))
    for device in devices:
        for prop in device.get("properties", []):
            if prop.get("name") == "maxPower" and "initValue" in prop:
                return str(prop["initValue"])
    raise SystemExit(
        "No 'maxPower' const with an initValue found in "
        f"{PV_DEVICES_FILE}. Ensure maxPower is declared at the #entity level in "
        "dtcPV.sysml (constAttributes inside a #component are dropped) and redeploy dtcPV."
    )


# --------------------------------------------------------------------------- #
# AWS: enable the fed-sysml-generated Strategy Lambda for Weather
# --------------------------------------------------------------------------- #
def inject_env(lambda_client, new_env: dict) -> None:
    try:
        current = lambda_client.get_function_configuration(FunctionName=STRATEGY_FUNCTION_NAME)
    except lambda_client.exceptions.ResourceNotFoundException:
        raise SystemExit(
            f"Strategy Lambda '{STRATEGY_FUNCTION_NAME}' not found. Run "
            "'continue fed-sysml' + 'fed terraform apply' first so fed-sysml "
            "creates it, then run this enablement step."
        )

    if current.get("LastUpdateStatus") == "InProgress":
        lambda_client.get_waiter("function_updated").wait(FunctionName=STRATEGY_FUNCTION_NAME)
        current = lambda_client.get_function_configuration(FunctionName=STRATEGY_FUNCTION_NAME)
    variables = dict(current.get("Environment", {}).get("Variables", {}))
    if current.get("LastUpdateStatus") != "Failed" and all(variables.get(key) == value for key, value in new_env.items()):
        print(f"Environment already configured for {STRATEGY_FUNCTION_NAME}")
        return
    variables.update(new_env)
    lambda_client.update_function_configuration(
        FunctionName=STRATEGY_FUNCTION_NAME,
        Environment={"Variables": variables},
    )
    lambda_client.get_waiter("function_updated").wait(FunctionName=STRATEGY_FUNCTION_NAME)
    print(f"Injected Weather connection env vars into {STRATEGY_FUNCTION_NAME}")


def grant_invoke(iam, weather_hot_reader_arn: str) -> None:
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["lambda:InvokeFunction"],
            "Resource": [weather_hot_reader_arn],
        }],
    }
    try:
        current = iam.get_role_policy(RoleName=STRATEGY_ROLE_NAME, PolicyName=INVOKE_POLICY_NAME)
    except iam.exceptions.NoSuchEntityException:
        current = {}
    if current.get("PolicyDocument") == policy:
        print(f"Invoke policy already configured for {STRATEGY_ROLE_NAME}")
        return
    try:
        iam.put_role_policy(
            RoleName=STRATEGY_ROLE_NAME,
            PolicyName=INVOKE_POLICY_NAME,
            PolicyDocument=json.dumps(policy),
        )
    except iam.exceptions.NoSuchEntityException:
        raise SystemExit(
            f"Strategy role '{STRATEGY_ROLE_NAME}' not found. Run "
            "'continue fed-sysml' + 'fed terraform apply' first."
        )
    print(f"Granted lambda:InvokeFunction on {weather_hot_reader_arn} to role {STRATEGY_ROLE_NAME}")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate deployment inputs without AWS calls.")
    args = parser.parse_args(argv)
    print("Running PV<->Weather federation enablement step (Weather side)...")

    weather = discover_weather()
    pv_production_device_id = discover_pv_production_device_id()
    pv_max_power = discover_pv_max_power()

    if args.check:
        print("PV/Weather deployment inputs are ready.")
        return

    try:
        import boto3
    except ImportError:
        raise SystemExit(
            "boto3 is required for the PV<->Weather enablement step. "
            "Install it (pip install boto3) and ensure AWS credentials are set."
        )

    region = weather["region"]
    lambda_client = boto3.client("lambda", region_name=region)
    iam = boto3.client("iam", region_name=region)

    env = {
        "WEATHER_HOT_READER_ARN": weather["hot_reader_arn"],
        "WEATHER_WORKSPACE_ID": weather["workspace_id"],
        "WEATHER_ENTITY_ID": weather["entity_id"],
        "WEATHER_COMPONENT_NAME": weather["component_name"],
        "PV_PRODUCTION_DEVICE_ID": pv_production_device_id,
        "PV_MAX_POWER": pv_max_power,
    }

    # Grant first, then inject: once env is present the Strategy Lambda will
    # attempt the Weather invoke, so the permission should already be in place.
    grant_invoke(iam, weather["hot_reader_arn"])
    inject_env(lambda_client, env)

    print("PV<->Weather federation enablement complete.")


if __name__ == "__main__":
    main()
