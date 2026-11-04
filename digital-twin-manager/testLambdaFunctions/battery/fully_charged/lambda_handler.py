import json
def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    event["who"] = "Battery Lambda Fully Charged"
    return {
        'statusCode': 200,
        'body': json.dumps(event)
    }