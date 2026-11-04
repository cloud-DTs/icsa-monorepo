import json
def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    event["who"] = "Battery Lambda Low Capacity"
    return {
        'statusCode': 200,
        'body': json.dumps(event)
    }