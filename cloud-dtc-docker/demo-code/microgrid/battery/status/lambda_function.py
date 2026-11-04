import json
from datetime import datetime, timezone


def lambda_handler(event, context):
    charge_value = event.get("chargeValue", 0.0)
    calculated_consumption = float(charge_value)

    return {
        "iotDeviceId": "SwiB9jTPm8kzDXz6chmo5T",
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "consumption": calculated_consumption,
    }
