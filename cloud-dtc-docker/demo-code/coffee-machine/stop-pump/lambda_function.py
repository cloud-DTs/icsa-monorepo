import json
import math
import operator


ACTION_DEFINITIONS = {
    "stopPumpForLowWater": {
        "command": "STOP",
        "reason": "low_water",
        "required_inputs": (
            "measuredLevel",
            "minimumLevel",
        ),
        "left_operand": "measuredLevel",
        "comparison": operator.lt,
        "operator_symbol": "<",
        "right_operand": "minimumLevel",
    },
    "stopPumpForHighPressure": {
        "command": "STOP",
        "reason": "high_brew_pressure",
        "required_inputs": (
            "measuredPressure",
            "maximumPressure",
        ),
        "left_operand": "measuredPressure",
        "comparison": operator.gt,
        "operator_symbol": ">",
        "right_operand": "maximumPressure",
    },
    "stopPumpForFullTray": {
        "command": "STOP",
        "reason": "drip_tray_full",
        "required_inputs": (
            "measuredLevel",
            "maximumLevel",
        ),
        "left_operand": "measuredLevel",
        "comparison": operator.gt,
        "operator_symbol": ">",
        "right_operand": "maximumLevel",
    },
}


def lambda_handler(event, context):
    action_name = _action_name(event)
    definition = _action_definition(action_name)

    values = _require_finite_numbers(
        event,
        definition["required_inputs"],
    )

    _require_action_condition(
        action_name,
        definition,
        values,
    )

    result = {
        "command": definition["command"],
        "reason": definition["reason"],
    }

    print(
        json.dumps(
            {
                "action": action_name,
                "inputs": values,
                "result": result,
            }
        )
    )

    return result


def _action_name(event):
    if not isinstance(event, dict):
        raise TypeError("event must be a dictionary")

    envelope = event.get("e", {})
    if not isinstance(envelope, dict):
        raise ValueError("event.e must be a dictionary")

    action = envelope.get("action", {})
    if not isinstance(action, dict):
        raise ValueError("event.e.action must be a dictionary")

    action_name = action.get("functionName")
    if not isinstance(action_name, str) or not action_name:
        raise ValueError(
            "event.e.action.functionName must be a non-empty string"
        )

    return action_name


def _action_definition(action_name):
    try:
        return ACTION_DEFINITIONS[action_name]
    except KeyError as error:
        raise ValueError(
            f"unsupported pump action: {action_name}"
        ) from error


def _require_finite_numbers(event, names):
    values = {}

    for name in names:
        value = event.get(name)

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a number")

        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite")

        values[name] = value

    return values


def _require_action_condition(action_name, definition, values):
    left_name = definition["left_operand"]
    right_name = definition["right_operand"]

    left_value = values[left_name]
    right_value = values[right_name]

    comparison = definition["comparison"]

    if comparison(left_value, right_value):
        return

    operator_symbol = definition["operator_symbol"]

    raise ValueError(
        f"{action_name} condition is not satisfied: "
        f"{left_name}={left_value} must be "
        f"{operator_symbol} "
        f"{right_name}={right_value}"
    )