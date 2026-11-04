import json


def lambda_handler(event, context):
    # No-op local trigger for dtcPV's "isCycling" strategyAction. The real
    # request-response work is done by the federation-owned Strategy Lambda that
    # fed-sysml generates from the "dtcPV.isCycling" reference in fedtwin.json.
    print("PV cycle trigger event: " + json.dumps(event))
    return {"statusCode": 200, "body": json.dumps(event)}
