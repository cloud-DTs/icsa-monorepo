import json


def lambda_handler(event, context):
    """No-op twin action used only as a federation event-registry trigger."""
    print("MEPSO trigger event: " + json.dumps(event))
    return {"statusCode": 200, "body": json.dumps(event)}
