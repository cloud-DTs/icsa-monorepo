import json
from time import time
from datetime import datetime, timezone
def lambda_handler(event, context):

    if isinstance(event.get("body"), str):
        event = json.loads(event["body"])
    kombi_data = event.get("ConsumptionStrategy", {})
    pv_data = kombi_data.get("production", {})
    battery_data = kombi_data.get("status", {})
    pv_power = pv_data.get("generatedPower", 0.0)
    charge_value = battery_data.get("chargeValue", 0.0)
    base_battery_consumption = float(charge_value) * 1.0
    effective_consumption = base_battery_consumption - float(pv_power)
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "iotDeviceId": "SwiB9jTPm8kzDXz6chmo5T",
            "time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "consumption": effective_consumption,
        })
    }