import json
def lambda_handler(event, context):
    print("Event: " + json.dumps(event))

    event["who"] = "FedTwin Combined Strategy Lambda"
    return {
        'statusCode': 200,
        'body': json.dumps(event)
    }