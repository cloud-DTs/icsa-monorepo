import json


def lambda_handler(event, context):
    # No-op local trigger for dtcCharger's "plugUpdate" strategyAction. The real
    # push to Battery is done by the federation-owned Strategy Lambda that
    # fed-sysml generates from the "dtcCharger.plugUpdate" reference in
    # fedtwin.json.
    print("Charger plug trigger event: " + json.dumps(event))
    return {"statusCode": 200, "body": json.dumps(event)}
