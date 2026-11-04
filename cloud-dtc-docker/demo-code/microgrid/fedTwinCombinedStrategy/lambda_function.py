import json
from datetime import datetime, timezone


def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    kombi_data = _collector_payload(event).get("dtc-ConsumptionStrategy", {})
    pv_data = kombi_data.get("production", {})
    battery_data = kombi_data.get("status", {})

    pv_power = pv_data.get("generatedPower", 0.0)
    charge_value = battery_data.get("chargeValue", 0.0)

    effective_consumption = float(charge_value) - float(pv_power)

    return {
        "statusCode": 200,
        "body": json.dumps({
            # dtc2bat's p16 device (isPlugged/charges/consumption) - resolved from
            # pipeline/digital-twin-manager/deployments/dtc2bat/input/config_iot_devices.json
            "iotDeviceId": "cPwQJsFpvFR6QsSxCiPHgo",
            "time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "consumption": effective_consumption,
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
