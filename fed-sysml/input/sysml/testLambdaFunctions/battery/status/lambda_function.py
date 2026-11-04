import json
from time import time
from datetime import datetime, timezone
def lambda_handler(event, context):
    current_charge = event.get("chargeValue", 0.0)
    
    calculated_consumption = float(current_charge) * 1.0
    
   
    iot_payload = {
        "iotDeviceId": "SwiB9jTPm8kzDXz6chmo5T",
        "time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "consumption": calculated_consumption
    }
    
    return iot_payload