import json
def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    event["who"] = "PV Lambda Low Output"
    return {
        'statusCode': 200,
        'body': json.dumps(event)
    }