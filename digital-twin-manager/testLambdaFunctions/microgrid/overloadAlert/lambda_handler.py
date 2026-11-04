import json
def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    event["who"] = "Microgrid Lambda Overload Alert"
    return {
        'statusCode': 200,
        'body': json.dumps(event)
    }