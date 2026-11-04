import json


def lambda_handler(event, context):
    print("Grid reading event: " + json.dumps(event))
    return {"statusCode": 200, "body": json.dumps(event)}
