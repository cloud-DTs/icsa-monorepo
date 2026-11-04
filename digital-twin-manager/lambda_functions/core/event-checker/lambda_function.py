import os
import json
import boto3
import urllib.request
from datetime import datetime, timezone, timedelta


with open(os.path.join(os.path.dirname(__file__), "config_events.json"), encoding="utf-8") as config_file:
    CONFIG_EVENTS = json.load(config_file)

DIGITAL_TWIN_NAME = os.environ["DIGITAL_TWIN_NAME"]
TWINMAKER_WORKSPACE_NAME = os.environ.get("TWINMAKER_WORKSPACE_NAME", None)
LAMBDA_CHAIN_STEP_FUNCTION_ARN = os.environ.get("LAMBDA_CHAIN_STEP_FUNCTION_ARN", None)
EVENT_FEEDBACK_LAMBDA_FUNCTION_ARN = os.environ.get("EVENT_FEEDBACK_LAMBDA_FUNCTION_ARN", None)
SSM_REGISTRY_PREFIX = os.environ.get("SSM_REGISTRY_PREFIX", None)

twinmaker_client = boto3.client("iottwinmaker")
lambda_client = boto3.client("lambda")
sf_client = boto3.client("stepfunctions")
ssm_client = boto3.client("ssm")


def unwrap_data_value(value):
    if not isinstance(value, dict) or len(value) != 1:
        return value
    key, val = next(iter(value.items()))
    if key == "listValue":
        return [unwrap_data_value(v) for v in val]
    if key == "mapValue":
        return {k: unwrap_data_value(v) for k, v in val.items()}
    return val


def fetch_value(entity_id, component_name, property_name):
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=24)

    try:
        response = twinmaker_client.get_property_value_history(
            workspaceId=TWINMAKER_WORKSPACE_NAME,
            entityId=entity_id,
            componentName=component_name,
            selectedProperties=[property_name],
            startTime=start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            endTime=end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            maxResults=1,
            orderByTime="DESCENDING"
        )
        print(f"fetch_value({property_name}) history response: {json.dumps(response, default=str)}")
        if not response.get("propertyValues"):
            print(f"fetch_value({property_name}) history: no propertyValues, returning None")
            return None
        entry = response["propertyValues"][0]
        if not entry.get("values"):
            print(f"fetch_value({property_name}) history: empty values list, returning None")
            return None
        return unwrap_data_value(entry["values"][0]["value"])

    except Exception as ex:
        print(f"fetch_value({property_name}) history call raised {type(ex).__name__}: {ex}, falling back to get_property_value")
        try:
            response = twinmaker_client.get_property_value(
                workspaceId=TWINMAKER_WORKSPACE_NAME,
                entityId=entity_id,
                componentName=component_name,
                selectedProperties=[property_name]
            )
            print(f"fetch_value({property_name}) latest response: {json.dumps(response, default=str)}")
            if not response.get("propertyValues"):
                print(f"fetch_value({property_name}) latest: no propertyValues, returning None")
                return None
            property = list(response["propertyValues"].values())[0]
            if not property.get("propertyValue"):
                print(f"fetch_value({property_name}) latest: no propertyValue, returning None")
                return None
            return unwrap_data_value(property["propertyValue"]["value"])
        except Exception as fallback_ex:
            print(f"fetch_value({property_name}) fallback call also raised {type(fallback_ex).__name__}: {fallback_ex}")
            raise


def extract_const_value(string):
    if string.startswith("DOUBLE(") and string.endswith(")"):
        return float(string[7:-1])
    elif string.startswith("INTEGER(") and string.endswith(")"):
        return int(string[8:-1])
    elif string.startswith("STRING(") and string.endswith(")"):
        return string[7:-1]
    return string


def is_typed_constant(value):
    return value.startswith(("DOUBLE(", "INTEGER(", "STRING(")) and value.endswith(")")


def resolve_condition_value(value):
    if is_typed_constant(value):
        return extract_const_value(value)
    if "." in value:
        return fetch_value(*value.split("."))
    return extract_const_value(value)


def resolve_input_parameters(e):
    input_params = {}
    for param in e["action"].get("inputParameters", []):
        if "value" in param:
            input_params[param["name"]] = param["value"]
        else:
            parts = param["id"].split(".")
            input_params[param["name"]] = fetch_value(parts[0], parts[1], parts[2])
    return input_params


def lookup_registry(event_name):
    if not SSM_REGISTRY_PREFIX:
        return None
    param_name = f"{SSM_REGISTRY_PREFIX}/{event_name}"
    try:
        response = ssm_client.get_parameter(Name=param_name)
        entry = json.loads(response["Parameter"]["Value"])
        print(f"FunctionRegistry hit for '{event_name}': {entry}")
        return entry.get("targets", [])
    except ssm_client.exceptions.ParameterNotFound:
        return None
    except Exception as ex:
        print(f"FunctionRegistry lookup failed (falling back to default): {ex}")
        return None


def resolve_lambda_arn(function_name):
    response = lambda_client.get_function(FunctionName=function_name)
    return response["Configuration"]["FunctionArn"]


def invoke_registry_target(entry, payload):
    address = entry["address"]
    target_type = entry.get("type") or entry.get("addressType")

    if not target_type:
        if ":lambda:" in address:
            target_type = "lambda"
        elif ":states:" in address:
            target_type = "step_function"

    normalized_type = str(target_type).lower().replace("-", "_")
    if normalized_type == "lambda":
        print(f"FunctionRegistry: invoking Lambda {address}")
        return lambda_client.invoke(
            FunctionName=address,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8")
        )

    if normalized_type in {"step_function", "stepfunctions", "states"}:
        print(f"FunctionRegistry: starting Step Function {address}")
        return sf_client.start_execution(
            stateMachineArn=address,
            input=json.dumps(payload)
        )

    raise ValueError(f"Unsupported FunctionRegistry target type '{target_type}' for {address}")


def fire_action(e, input_params, registry_entry):
    action = e["action"]
    has_feedback = "feedback" in action
    payload = {"e": e, **input_params}
    print(f"Fire action {action}")
    if registry_entry:
        for entry in registry_entry:
            invoke_registry_target(entry, payload)
        return

    #Default execution
    function_name = DIGITAL_TWIN_NAME + "-" + action["functionName"]
    if not has_feedback:
        lambda_client.invoke(FunctionName=function_name, InvocationType="Event", Payload=json.dumps(payload).encode("utf-8"))
    else:
        print(f"Invoking Lambda function {function_name} with feedback")
        action_function_arn = resolve_lambda_arn(function_name)
        response = sf_client.start_execution(
            stateMachineArn=LAMBDA_CHAIN_STEP_FUNCTION_ARN,
            input=json.dumps({
                "LambdaAArn": action_function_arn,
                "LambdaBArn": EVENT_FEEDBACK_LAMBDA_FUNCTION_ARN,
                "InputData": payload
            })
        )
        print(f"Step Function started! Response: {json.dumps(response, default=str)}")

def lambda_handler(event, context):
    print("Hello from Event-Checker!")
    print("Event: " + json.dumps(event))

    trigger_keys = set(event.keys()) - {"iotDeviceId", "time"}
    print(f"Trigger keys: {trigger_keys}")

    for e in CONFIG_EVENTS:
        try:
            condition = e["condition"]
            param1, operation, param2 = condition.split()

            condition_properties = {
                p.split(".")[-1]
                for p in [param1, param2]
                if "." in p and not is_typed_constant(p)
            }
            print(f"Checking condition '{condition}' — relevant properties: {condition_properties}")

            if trigger_keys and not trigger_keys.intersection(condition_properties):
                print(f"Skipping — trigger {trigger_keys} not relevant for {condition_properties}")
                continue

            param1_value = resolve_condition_value(param1)
            if param1_value is None:
                print(f"No value yet for {param1}, skipping event")
                continue

            param2_value = resolve_condition_value(param2)
            if param2_value is None:
                print(f"No value yet for {param2}, skipping event")
                continue

            print(f"Evaluating: {param1_value} {operation} {param2_value}")

            match operation:
                case "<":  result = param1_value < param2_value
                case ">":  result = param1_value > param2_value
                case "==": result = param1_value == param2_value
                case _:    raise ValueError(f"Unknown operator: {operation}")

            print(f"Condition result: {result}")

            if e["action"]["type"] == "lambda" and result:
                input_params = resolve_input_parameters(e)
                print(f"Resolved input_params: {input_params}")
                registry_entry = lookup_registry(e["action"]["functionName"])
                fire_action(e, input_params, registry_entry)
            else:
                print(f"Condition false or action type not lambda — not firing")

        except Exception as ex:
            print(f"Something went wrong for condition '{e.get('condition', '?')}': {ex}")
