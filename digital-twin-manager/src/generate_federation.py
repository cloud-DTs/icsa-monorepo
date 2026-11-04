import json
import globals


def generate_federation_input():
    region = globals.config_credentials["aws_region"]
    ssm_prefix = globals.ssm_registry_prefix()
    workspace_id = globals.twinmaker_workspace_name()

    strategies = []
    for e in globals.config_events:
        strategies.append({
            "eventName": e["action"]["functionName"],
            "inputParameters": e["action"].get("inputParameters", []),
            "outputParameters": e["action"].get("outputParameters", [])
        })

    hot_reader_arn = globals.aws_lambda_client.get_function(
        FunctionName=globals.hot_reader_lambda_function_name()
    )["Configuration"]["FunctionArn"]

    output = {
        "name": globals.config["digital_twin_name"],
        "region": region,
        "ssm_registry_prefix": ssm_prefix,
        "hot_reader_arn": hot_reader_arn,
        "strategies": strategies,
        "twinmaker_workspace_id": workspace_id
    }

    with open(f"{globals.config['digital_twin_name']}_federation_input.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"Generated {globals.config['digital_twin_name']}_federation_input.json")
