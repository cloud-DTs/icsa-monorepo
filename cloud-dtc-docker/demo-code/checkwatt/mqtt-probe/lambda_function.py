"""Echo one CheckWatt measurement for MQTT roundtrip evaluation."""

import json
import math


def lambda_handler(event, context):
    value = event.get("powerKW")
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("powerKW must be a finite number")

    result = {"mock": True, "action": "mqttProbe", "value": value}
    print(json.dumps(result, allow_nan=False))
    return result
