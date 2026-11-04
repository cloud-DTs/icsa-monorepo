import json
import os
from datetime import datetime, timedelta, timezone

import boto3

from decision_logic import (
    calculate_power_split,
    grid_power_drawn,
    net_battery_power,
    next_state_of_charge,
    signed_power,
)

# Federation-owned Strategy Lambda for dtc-BatteryChargerDecisionStrategy.
#
# fed-sysml generates this function plus its Step Function, Collector, Feedback
# and IAM from the fedtwin.json entry. What fed-sysml cannot express is supplied
# by scripts/federate_battery_charger_decision.py AFTER `fed terraform apply`:
# the two hot-reader ARNs + lambda:InvokeFunction on them, the Charger target
# device id, and Battery's #constAttribute value (consts are not collectible).
GRID_HOT_READER_ARN = os.environ.get("GRID_HOT_READER_ARN")
GRID_WORKSPACE_ID = os.environ.get("GRID_WORKSPACE_ID")
GRID_ENTITY_ID = os.environ.get("GRID_ENTITY_ID")
GRID_SENSOR_COMPONENT = os.environ.get("GRID_SENSOR_COMPONENT")

BATTERY_HOT_READER_ARN = os.environ.get("BATTERY_HOT_READER_ARN")
BATTERY_WORKSPACE_ID = os.environ.get("BATTERY_WORKSPACE_ID")
BATTERY_ENTITY_ID = os.environ.get("BATTERY_ENTITY_ID")
BATTERY_STORAGE_COMPONENT = os.environ.get("BATTERY_STORAGE_COMPONENT")
BATTERY_EXTERNAL_INPUTS_COMPONENT = os.environ.get("BATTERY_EXTERNAL_INPUTS_COMPONENT")

CHARGER_ACT_CHARGE_DEVICE_ID = os.environ.get("CHARGER_ACT_CHARGE_DEVICE_ID")
# All three are #constAttribute values, injected from their deployed initValue by
# the enablement step - consts are not collectible through the Collector.
BATTERY_MAX_CHARGING_POWER = os.environ.get("BATTERY_MAX_CHARGING_POWER")
BATTERY_MAX_DISCHARGING_POWER = os.environ.get("BATTERY_MAX_DISCHARGING_POWER")
BATTERY_TOTAL_CAPACITY = os.environ.get("BATTERY_TOTAL_CAPACITY")
CHARGER_MAX_POWER = os.environ.get("CHARGER_MAX_POWER")

# Where the recomputed state of charge is published. Separate from the feedback
# topic, which carries the Charger result.
BATTERY_STORAGE_DEVICE_ID = os.environ.get("BATTERY_STORAGE_DEVICE_ID")
BATTERY_IOT_TOPIC = os.environ.get("BATTERY_IOT_TOPIC")

iot_client = boto3.client("iot-data")

STRATEGY_NAME = "dtc-BatteryChargerDecisionStrategy"
TRIGGER_EVENT_NAME = "plugDecision"

# How far back to look when reading the latest value of a property.
LOOKBACK_HOURS = 24

lambda_client = boto3.client("lambda")

REQUIRED_ENV = {
    "GRID_HOT_READER_ARN": GRID_HOT_READER_ARN,
    "GRID_WORKSPACE_ID": GRID_WORKSPACE_ID,
    "GRID_ENTITY_ID": GRID_ENTITY_ID,
    "GRID_SENSOR_COMPONENT": GRID_SENSOR_COMPONENT,
    "BATTERY_HOT_READER_ARN": BATTERY_HOT_READER_ARN,
    "BATTERY_WORKSPACE_ID": BATTERY_WORKSPACE_ID,
    "BATTERY_ENTITY_ID": BATTERY_ENTITY_ID,
    "BATTERY_STORAGE_COMPONENT": BATTERY_STORAGE_COMPONENT,
    "BATTERY_EXTERNAL_INPUTS_COMPONENT": BATTERY_EXTERNAL_INPUTS_COMPONENT,
    "CHARGER_ACT_CHARGE_DEVICE_ID": CHARGER_ACT_CHARGE_DEVICE_ID,
    "BATTERY_MAX_CHARGING_POWER": BATTERY_MAX_CHARGING_POWER,
    "BATTERY_MAX_DISCHARGING_POWER": BATTERY_MAX_DISCHARGING_POWER,
    "BATTERY_TOTAL_CAPACITY": BATTERY_TOTAL_CAPACITY,
    "CHARGER_MAX_POWER": CHARGER_MAX_POWER,
    "BATTERY_STORAGE_DEVICE_ID": BATTERY_STORAGE_DEVICE_ID,
    "BATTERY_IOT_TOPIC": BATTERY_IOT_TOPIC,
}


def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    missing = [name for name, value in REQUIRED_ENV.items() if not value]
    if missing:
        raise RuntimeError(
            "Battery->Charger decision federation not fully established. Missing "
            f"env vars: {missing}. Run scripts/federate_battery_charger_decision.py "
            "after 'fed terraform apply'."
        )

    # What the Collector delivered - logged for diagnostics only. It is NOT used
    # as the source of truth: the Collector reads the hot-reader WITHOUT a time
    # range, which returns only the single latest DynamoDB record for the device.
    # dtcBattery.storage receives isPlugged (from the Charger federation) and
    # charge (from the simulator) in SEPARATE messages, so whichever arrived last
    # wins and the other property is simply absent from the Collector payload.
    collector = _collector_payload(event).get(STRATEGY_NAME, {}).get(TRIGGER_EVENT_NAME, {})
    print("DIAG collector payload: " + json.dumps(collector, default=str))

    # Everything is read explicitly with a time range, which makes the hot-reader
    # return every record containing the property, so a value is found regardless
    # of which message happened to be last.
    storage_times = {}
    battery_storage = _pull(
        "Battery.storage", BATTERY_HOT_READER_ARN, BATTERY_WORKSPACE_ID,
        BATTERY_ENTITY_ID, BATTERY_STORAGE_COMPONENT,
        {"isPlugged": "STRING", "charge": "DOUBLE"},
        timestamps=storage_times,
    )
    battery_inputs = _pull(
        "Battery.externalInputs", BATTERY_HOT_READER_ARN, BATTERY_WORKSPACE_ID,
        BATTERY_ENTITY_ID, BATTERY_EXTERNAL_INPUTS_COMPONENT,
        {"generatedPower": "DOUBLE", "greenEnergyPercentage": "DOUBLE",
         "maxPower": "DOUBLE"},
    )
    # PULL / REQUEST to the Grid twin - the exchange mode. The price is used for
    # the decision only; it is deliberately not written back to Battery.
    grid_sensor = _pull(
        "Grid.sensor", GRID_HOT_READER_ARN, GRID_WORKSPACE_ID,
        GRID_ENTITY_ID, GRID_SENSOR_COMPONENT,
        {"currentElectricityPrice": "DOUBLE"},
    )

    is_plugged = _as_bool(battery_storage.get("isPlugged"))
    charge = _as_float(battery_storage.get("charge"))
    generated_power = _as_float(battery_inputs.get("generatedPower"))
    green_energy = _as_float(battery_inputs.get("greenEnergyPercentage"))
    grid_max_power = _as_float(battery_inputs.get("maxPower"))
    electricity_price = _as_float(grid_sensor.get("currentElectricityPrice"))

    act_charge_ev, battery_charge_power = calculate_power_split(
        green_energy_percentage=green_energy,
        pv_production=generated_power,
        grid_max_power=grid_max_power,
        charger_max_power=_as_float(CHARGER_MAX_POWER),
        battery_max_charging_power=_as_float(BATTERY_MAX_CHARGING_POWER),
        battery_max_discharging_power=_as_float(BATTERY_MAX_DISCHARGING_POWER),
        is_plugged=is_plugged,
        electricity_price=electricity_price,
        battery_charge_percent=charge,
    )

    print("DIAG inputs: " + json.dumps({
        "isPlugged": is_plugged, "charge": charge,
        "generatedPower": generated_power, "greenEnergyPercentage": green_energy,
        "gridMaxPower": grid_max_power, "electricityPrice": electricity_price,
        "chargerMaxPower": _as_float(CHARGER_MAX_POWER),
        "batteryMaxCharging": _as_float(BATTERY_MAX_CHARGING_POWER),
        "batteryMaxDischarging": _as_float(BATTERY_MAX_DISCHARGING_POWER),
        "totalCapacity": _as_float(BATTERY_TOTAL_CAPACITY),
    }))
    # What the Charger reports as actBatteryCharge is the SIGNED battery power:
    # positive while the battery is being charged, negative while it is the one
    # feeding the car. battery_charge_power on its own only ever covers the
    # charging half, so on a brown grid it would sit at 0 and hide the drain.
    net_power = signed_power(
        net_battery_power(
            green_energy_percentage=green_energy,
            act_charge_ev=act_charge_ev,
            battery_charge_power=battery_charge_power,
            battery_max_discharging_power=_as_float(BATTERY_MAX_DISCHARGING_POWER),
            battery_charge_percent=charge,
        ),
        _as_float(BATTERY_MAX_CHARGING_POWER),
        _as_float(BATTERY_MAX_DISCHARGING_POWER),
    )
    grid_power = grid_power_drawn(
        green_energy_percentage=green_energy,
        pv_production=generated_power,
        act_charge_ev=act_charge_ev,
        battery_charge_power=battery_charge_power,
    )

    print("DIAG actChargeEV: " + json.dumps(act_charge_ev)
          + " | actBatteryCharge: " + json.dumps(net_power)
          + " | gridPower: " + json.dumps(grid_power))

    # --- state of charge -----------------------------------------------------
    # Integrate the same signed power over the time since the last charge
    # reading, then publish it back to dtcBattery together with gridPower. This
    # is a SEPARATE publish, not the feedback: a federation has one feedback
    # topic and that one belongs to the Charger. Safe to write into dtcBattery
    # because the message carries only charge and gridPower, neither of which
    # matches any of dtcBattery's trigger conditions.
    elapsed = _seconds_since(storage_times.get("charge"))
    new_charge = next_state_of_charge(
        current_percent=charge,
        net_power_kw=net_power,
        total_capacity_kwh=_as_float(BATTERY_TOTAL_CAPACITY),
        elapsed_seconds=elapsed,
    )
    print(f"DIAG soc: {charge} % + net {net_power:+.2f} kW over {elapsed}s"
          f" -> {new_charge} %")
    _publish_battery_state(new_charge, grid_power)

    # Feedback publishes this to dtcCharger/iot-data; ingestion routes by
    # iotDeviceId to write dtcCharger.chargerState.actChargeEV. The
    # {"statusCode", "body": json.dumps(...)} envelope is REQUIRED - the shared
    # Feedback Lambda reads strategyResult["body"] as a JSON string.
    # Both halves of the split ride in ONE message to the same Charger device:
    # one federation, one calculation, one set of pulls. Nothing is written back
    # into dtcBattery, so the decision cannot re-trigger itself.
    return {
        "statusCode": 200,
        "body": json.dumps({
            "iotDeviceId": CHARGER_ACT_CHARGE_DEVICE_ID,
            "time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "actChargeEV": act_charge_ev,
            "actBatteryCharge": net_power,
        }),
    }


def _pull(label, hot_reader_arn, workspace_id, entity_id, component_name, properties,
          timestamps=None):
    """Read the latest value of each property from one component.

    If a dict is passed as `timestamps`, it is filled with the ISO timestamp of
    each value that was found - needed to integrate the state of charge.

    Uses the hot-reader's TIME-RANGE branch on purpose. Without startTime/endTime
    the hot-reader returns only the single most recent DynamoDB record, and a
    property that arrived in an earlier message would be missing. Read the range
    newest-first: the hot-reader caps its scan, so ascending order can return only
    old records once telemetry accumulates. Request one value per property to keep
    the response small while still reading properties sent in separate messages.

    Note the two branches return DIFFERENT shapes: the time-range branch returns
    propertyValues as a LIST of {entityPropertyReference, values[]}, while the
    plain branch returns a DICT keyed by property name. This parses the list form.
    """
    if timestamps is None:
        timestamps = {}

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=LOOKBACK_HOURS)

    request_payload = {
        "workspaceId": workspace_id,
        "entityId": entity_id,
        "componentName": component_name,
        "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%S.999Z"),
        "orderByTime": "DESCENDING",
        "maxResults": 1,
        "selectedProperties": list(properties.keys()),
        "properties": {
            name: {"definition": {"dataType": {"type": data_type}}}
            for name, data_type in properties.items()
        },
    }

    try:
        response = lambda_client.invoke(
            FunctionName=hot_reader_arn,
            InvocationType="RequestResponse",
            Payload=json.dumps(request_payload).encode("utf-8"),
        )
        result = json.loads(response["Payload"].read())
    except Exception as error:  # noqa: BLE001 - a failed pull must not kill the run
        print(f"DIAG {label} pull failed: {error}")
        return {}

    print(f"DIAG raw {label} response: " + json.dumps(result, default=str)[:1500])

    values = {}
    property_values = result.get("propertyValues")
    if not isinstance(property_values, list):
        print(f"DIAG {label}: unexpected propertyValues shape, got {type(property_values)}")
        return values

    for entry in property_values:
        name = entry.get("entityPropertyReference", {}).get("propertyName")
        history = entry.get("values") or []
        if not name or not history:
            continue
        # The hot-reader preserves the requested descending timestamp order.
        newest = history[0]
        raw_value = newest.get("value", {})
        if raw_value:
            values[name] = list(raw_value.values())[0]
            # Keep the timestamp too: the state of charge integrates over the
            # time since this value was written, so the reading is useless
            # without knowing when it was taken.
            timestamps[name] = newest.get("time")

    print(f"DIAG {label} resolved: " + json.dumps(values, default=str))
    return values


def _seconds_since(iso_timestamp):
    """Real seconds between an ISO-8601 UTC timestamp and now.

    Returns None when the timestamp is missing or unparseable, which
    next_state_of_charge treats as "no elapsed time" and leaves the SoC alone -
    better than guessing an interval and moving the battery by a wrong amount.
    """
    if not iso_timestamp:
        return None
    try:
        text = str(iso_timestamp).replace("Z", "+00:00")
        then = datetime.fromisoformat(text)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as error:
        print(f"DIAG could not parse timestamp {iso_timestamp!r}: {error}")
        return None
    return max(0.0, (datetime.now(timezone.utc) - then).total_seconds())


def _publish_battery_state(new_charge, grid_power):
    """Publish charge + gridPower straight to dtcBattery's ingestion topic.

    Not through Feedback - that one is bound to dtcCharger. Both values live on
    the same storage device, so one message covers them. A failure here must not
    lose the Charger result, which is why it is caught and logged.
    """
    payload = {
        "iotDeviceId": BATTERY_STORAGE_DEVICE_ID,
        "time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "charge": new_charge,
        "gridPower": grid_power,
    }
    try:
        iot_client.publish(
            topic=BATTERY_IOT_TOPIC, qos=1, payload=json.dumps(payload)
        )
        print(f"DIAG published to {BATTERY_IOT_TOPIC}: {json.dumps(payload)}")
    except Exception as error:  # noqa: BLE001
        print(f"DIAG publishing charge failed: {error}")


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_bool(value):
    return str(value).strip().lower() in ("true", "1", "yes")


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
