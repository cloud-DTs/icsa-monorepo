import json
from datetime import datetime, timezone

# Replaced by deployment preparation from the Battery converter output.
# Never commit the generated device ID.
BATTERY_VIRTUAL_SENSOR_ID = "__INJECTED_BY_PIPELINE__"


def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    if BATTERY_VIRTUAL_SENSOR_ID == "__INJECTED_BY_PIPELINE__":
        raise RuntimeError("Battery virtual sensor ID was not injected before deployment")

    return {
        "iotDeviceId": BATTERY_VIRTUAL_SENSOR_ID,
        "time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "pvGeneratedPower": event.get("generatedPower", 0.0)
    }
