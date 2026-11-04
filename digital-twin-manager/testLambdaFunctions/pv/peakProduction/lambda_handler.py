import json
def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    event["who"] = "PV Lambda Peak Production"
    return {
        'statusCode': 200,
        'body': json.dumps(event)
    }