import json
import os
from datetime import datetime, timezone

import boto3

# Federation-owned Strategy Lambda for dtc-PVWeatherStrategy. fed-sysml generates
# this function and its Step Function/Collector/Feedback/IAM. But dtcWeather is
# passive (no strategyAction) and the requested hour is dynamic, so fed-sysml
# CANNOT wire Weather in: these env vars and the InvokeFunction permission on
# Weather's hot-reader are supplied by the federation enablement step
# (scripts/federate_pv_weather.py), which runs after `fed terraform apply`.
#
# Before that step: env unset AND no invoke permission -> this fails two ways.
WEATHER_HOT_READER_ARN = os.environ.get("WEATHER_HOT_READER_ARN")
WEATHER_WORKSPACE_ID = os.environ.get("WEATHER_WORKSPACE_ID")
WEATHER_ENTITY_ID = os.environ.get("WEATHER_ENTITY_ID")
WEATHER_COMPONENT_NAME = os.environ.get("WEATHER_COMPONENT_NAME")
PV_PRODUCTION_DEVICE_ID = os.environ.get("PV_PRODUCTION_DEVICE_ID")
# maxPower is a static constant (PV's own), so it is injected as an env var by the
# federation enablement step - NOT collected. No working federation collects a
# #constAttribute through the Collector, and a const can't be delivered as a 2nd
# strategyAction inputParameter.
PV_MAX_POWER = os.environ.get("PV_MAX_POWER")

STRATEGY_NAME = "dtc-PVWeatherStrategy"
TRIGGER_EVENT_NAME = "isCycling"

lambda_client = boto3.client("lambda")


def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    if not all([
        WEATHER_HOT_READER_ARN, WEATHER_WORKSPACE_ID, WEATHER_ENTITY_ID,
        WEATHER_COMPONENT_NAME, PV_PRODUCTION_DEVICE_ID, PV_MAX_POWER,
    ]):
        raise RuntimeError(
            "PV<->Weather federation not fully established: Weather connection env "
            "vars are missing. Run the federation enablement step "
            "(scripts/federate_pv_weather.py) after 'fed terraform apply'."
        )

    # Collector delivers PV's current values under {strategyName: {eventName: {...}}}.
    data = _collector_payload(event).get(STRATEGY_NAME, {}).get(TRIGGER_EVENT_NAME, {})
    hours_cycle = int(float(data.get("hours_cycle", 0)))
    # maxPower from the federation-injected env var, not the Collector.
    max_power = float(PV_MAX_POWER)

    # Dynamic hour -> property name: 11 -> "hour11", 2 -> "hour02".
    hour_property = f"hour{hours_cycle:02d}"

    request_payload = {
        "workspaceId": WEATHER_WORKSPACE_ID,
        "entityId": WEATHER_ENTITY_ID,
        "componentName": WEATHER_COMPONENT_NAME,
        "selectedProperties": [hour_property],
        "properties": {
            hour_property: {"definition": {"dataType": {"type": "DOUBLE"}}}
        },
    }

    # Requires lambda:InvokeFunction on Weather's hot-reader - granted only by
    # the federation enablement step. AccessDenied before federation.
    response = lambda_client.invoke(
        FunctionName=WEATHER_HOT_READER_ARN,
        InvocationType="RequestResponse",
        Payload=json.dumps(request_payload).encode("utf-8"),
    )

    result = json.loads(response["Payload"].read())
    prop = result.get("propertyValues", {}).get(hour_property)
    percentage = 0.0
    if prop and "propertyValue" in prop:
        value_dict = prop["propertyValue"]["value"]
        percentage = float(list(value_dict.values())[0])

    # --- Diagnostic logging (identify which input is zero) ---
    print("DIAG hours_cycle: " + json.dumps(hours_cycle))
    print("DIAG max_power: " + json.dumps(max_power))
    print("DIAG requested Weather property: " + hour_property)
    print("DIAG raw Weather hot-reader response: " + json.dumps(result))
    print("DIAG percentage: " + json.dumps(percentage))
    # --- end diagnostic logging ---

    production = max_power * (percentage / 100.0)

    print("DIAG final production: " + json.dumps(production))

    # Returned to the Feedback Lambda, which reads strategyResult["body"] (a JSON
    # string), then publishes it to dtcPV/iot-data; ingestion routes by
    # iotDeviceId to write dtcPV.production. The {"statusCode", "body": json.dumps(
    # ...)} envelope is REQUIRED - it matches every other working Strategy Lambda
    # (fedTwinCombinedStrategy / fedGridToBatteryPush / fedPvToBatteryPush) and the
    # shared Feedback Lambda's parser. Returning the fields directly (no "body")
    # makes Feedback publish "{}" and the value is lost.
    return {
        "statusCode": 200,
        "body": json.dumps({
            "iotDeviceId": PV_PRODUCTION_DEVICE_ID,
            "time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "production": production,
        }),
    }


def _collector_payload(event):
    body = event.get("body")
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    if isinstance(body, dict):
        return body
    return event
