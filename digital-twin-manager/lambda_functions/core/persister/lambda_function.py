import os
import json
import time
import boto3
from decimal import Decimal

DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", None)
EVENT_CHECKER_LAMBDA_NAME = os.environ.get("EVENT_CHECKER_LAMBDA_NAME", None)
DEBUG = os.environ.get("DEBUG", "false").strip().lower() == "true"

dynamodb_client = boto3.resource("dynamodb")
dynamodb_table = dynamodb_client.Table(DYNAMODB_TABLE_NAME)
twinmaker_client = boto3.client("iottwinmaker")
lambda_client = boto3.client("lambda")


def floats_to_decimals(obj):
    if isinstance(obj, list):
        return [floats_to_decimals(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj

def lambda_handler(event, context):
    print("Hello from Persister!")
    print("Event: " + json.dumps(event))

    item = event.copy()
    item["id"] = str(item.pop("time"))
    item = floats_to_decimals(item)

    if DEBUG:
        ingested_at_ms = event.get("iot_ingested_at_ms")
        if type(ingested_at_ms) is not int:
            ingested_at_ms = None
        # This is the request start time; DynamoDB does not return a commit timestamp.
        item["db_write_started_at_ms"] = time.time_ns() // 1_000_000
        if ingested_at_ms is not None:
            item["ingestion_to_write_ms"] = item["db_write_started_at_ms"] - ingested_at_ms

    dynamodb_table.put_item(Item=item)

    if DEBUG:
        acknowledged_at_ms = time.time_ns() // 1_000_000
        timing = {
            "event": "telemetry_persisted",
            "entry_point": "persister",
            "request_id": getattr(context, "aws_request_id", None),
            "iotDeviceId": item.get("iotDeviceId"),
            "id": item["id"],
            "iot_ingested_at_ms": ingested_at_ms,
            "db_write_started_at_ms": item["db_write_started_at_ms"],
            "db_write_ack_at_ms": acknowledged_at_ms,
        }
        if ingested_at_ms is not None:
            timing["ingestion_to_write_ms"] = item["ingestion_to_write_ms"]
            timing["ingestion_to_ack_ms"] = acknowledged_at_ms - ingested_at_ms
        print(json.dumps(timing))

    lambda_client.invoke(FunctionName=EVENT_CHECKER_LAMBDA_NAME, InvocationType="Event", Payload=json.dumps(event).encode("utf-8"))
