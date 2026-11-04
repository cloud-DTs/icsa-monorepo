"""Temporary mock for the MGrid energy-management actions."""

import json


def lambda_handler(event, context):
    action_name = event.get("e", {}).get("action", {}).get("functionName", "balance")
    inputs = {
        name: event[name]
        for name in (
            "charger1Power",
            "charger2Power",
            "charger3Power",
            "charger4Power",
            "charger5Power",
            "batteryPower",
            "pvPower",
        )
        if name in event
    }
    result = {
        "mock": True,
        "action": action_name,
        "inputs": inputs,
        "message": "Energy management is not implemented yet.",
    }
    print(json.dumps(result))
    return result
