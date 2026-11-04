import json
import os
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key

DIGITAL_TWIN_NAME = os.environ["DIGITAL_TWIN_NAME"]
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", None)

SCAN_LIMIT = 500
PAGE_SIZE = 200

twinmaker_client = boto3.client("iottwinmaker")
dynamodb_resource = boto3.resource("dynamodb")
dynamodb_table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)


def to_native(value, raw_type):
    if isinstance(value, Decimal):
        if raw_type in ("INTEGER", "LONG"):
            return int(value)
        return float(value)
    return value


def scan_items(key_condition, scan_forward):
    items = []
    last_evaluated_key = None
    while len(items) < SCAN_LIMIT:
        query_kwargs = dict(
            KeyConditionExpression=key_condition,
            ScanIndexForward=scan_forward,
            Limit=PAGE_SIZE,
        )
        if last_evaluated_key:
            query_kwargs["ExclusiveStartKey"] = last_evaluated_key
        db_response = dynamodb_table.query(**query_kwargs)
        items.extend(db_response.get("Items", []))
        last_evaluated_key = db_response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break
    return items


def resolve_iot_device_id(event, component_info):
    if not isinstance(component_info, dict):
        raise ValueError(f"TwinMaker component not found: {event['componentName']}")

    properties = component_info.get("properties", {})
    if "iotDeviceId" in properties:
        device_property = properties["iotDeviceId"]
        value = device_property.get("value", {}) if isinstance(device_property, dict) else {}
        device_id = value.get("stringValue") if isinstance(value, dict) else None
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError(f"Component {event['componentName']} has no valid iotDeviceId value.")
        return device_id

    component_type_id = component_info.get("componentTypeId")
    prefix = DIGITAL_TWIN_NAME + "-"
    if not isinstance(component_type_id, str) or not component_type_id.startswith(prefix):
        raise ValueError("Cannot derive an IoT device ID from an external component type.")

    # Old managed types used the device ID as their suffix and had no native ID property.
    component_type = twinmaker_client.get_component_type(
        workspaceId=event["workspaceId"], componentTypeId=component_type_id,
    )
    if "iotDeviceId" in component_type.get("propertyDefinitions", {}):
        raise ValueError(f"Component {event['componentName']} is missing its iotDeviceId value.")
    device_id = component_type_id.removeprefix(prefix)
    if not device_id:
        raise ValueError("Legacy component type has an empty IoT device ID.")
    return device_id


def lambda_handler(event, context):
    entity = twinmaker_client.get_entity(workspaceId=event["workspaceId"], entityId=event["entityId"])
    components = entity.get("components", {})
    component_info = components.get(event["componentName"])
    iot_device_id = resolve_iot_device_id(event, component_info)

    start_time = event.get("startTime")
    end_time = event.get("endTime")

    if start_time and end_time:
        order_by_time = event.get("orderByTime", "ASCENDING")
        scan_forward = (order_by_time != "DESCENDING")
        max_results = event.get("maxResults")

        key_condition = Key("iotDeviceId").eq(iot_device_id) & Key("id").between(start_time, end_time)
        items = scan_items(key_condition, scan_forward)

        property_values = []
        for property_name in event["selectedProperties"]:
            raw_type = event["properties"][property_name]["definition"]["dataType"]["type"]
            property_type_key = raw_type.lower() + "Value"
            entry = {
                "entityPropertyReference": {"propertyName": property_name},
                "values": []
            }
            for item in items:
                if property_name in item and item[property_name] is not None:
                    entry["values"].append({
                        "time": item["id"],
                        "value": {property_type_key: to_native(item[property_name], raw_type)}
                    })
                    if max_results and len(entry["values"]) >= max_results:
                        break
            property_values.append(entry)
        return {"propertyValues": property_values}

    else:
        key_condition = Key("iotDeviceId").eq(iot_device_id)
        items = scan_items(key_condition, scan_forward=False)
        property_values = {}

        for property_name in event["selectedProperties"]:
            raw_type = event["properties"][property_name]["definition"]["dataType"]["type"]
            property_type_key = raw_type.lower() + "Value"

            for item in items:
                if property_name in item and item[property_name] is not None:
                    property_values[property_name] = {
                        "propertyReference": {
                            "propertyName": property_name,
                            "componentName": event["componentName"],
                            "entityId": event["entityId"]
                        },
                        "propertyValue": {
                            "value": {
                                property_type_key: to_native(item[property_name], raw_type)
                            },
                            "timestamp": item["id"]
                        }
                    }
                    break

        return {"propertyValues": property_values}
