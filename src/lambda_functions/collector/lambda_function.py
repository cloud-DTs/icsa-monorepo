from typing import List, Optional, Union
import json
import os
import boto3

class ParameterInfo():
    name: str
    dataType: str
    value: Optional[Union[str, float, int]] = None
    hot_reader_arn: Optional[str] = None
    region: Optional[str] = None
    component_name: Optional[str] = None
    property_name: Optional[str] = None
    workspace_id: Optional[str] = None
    entity_id: Optional[str] = None
    strategy_name: Optional[str] = None
    has_configured_value: bool = False

    @staticmethod
    def parseInfo(data):
        param = ParameterInfo()
        param.name = data["name"]
        param.has_configured_value = "value" in data
        param.value = data.get("value")
        param.hot_reader_arn = data.get("hot_reader_arn", None)
        param.region = data.get("region", None)
        param.dataType = data.get("dataType", None)
        param.component_name = data.get("component_name", None)
        param.property_name = data.get("property_name", None)
        param.workspace_id = data.get("workspace_id", None)
        param.entity_id = data.get("entity_id", None)
        param.strategy_name = data.get("strategy_name", None)
        return param

    def fetch_value(self):
        if self.hot_reader_arn:
            lambda_client = boto3.client("lambda", region_name=self.region)
        
            payload = {
                "workspaceId": self.workspace_id,
                "entityId": self.entity_id,
                "componentName": self.component_name,
                "selectedProperties": [self.property_name],
                "properties": {
                    self.property_name: {
                        "definition": {
                            "dataType": {"type": self.dataType}
                        }
                    }
                }
            }
        
            response = lambda_client.invoke(
                FunctionName=self.hot_reader_arn,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload).encode("utf-8")
            )

            result = json.loads(response["Payload"].read())
            if response.get("FunctionError"):
                raise RuntimeError(
                    f"Hot reader '{self.hot_reader_arn}' failed: {json.dumps(result)}"
                )
            prop = result["propertyValues"].get(self.property_name)
            if prop:
                value_dict = prop["propertyValue"]["value"]
                self.value = list(value_dict.values())[0]
                return

        if self.has_configured_value:
            return

        print(f"Warning: No value fetched for parameter '{self.name}'")
        self.value = None


class Parameters:

    def __init__(self, triggered_strategy: str):
        self.triggered_strategy = triggered_strategy
        self.parameterInfos: dict[str, dict[str, list[ParameterInfo]]] = {}

    def parse_parameters(self, param_info: dict):
        matched_combined_strategies = []
        for comb_strat_name, param_list in param_info.items():
            for p in param_list:
                if p.get("strategy_name") == self.triggered_strategy:
                    matched_combined_strategies.append(comb_strat_name)
                    break 

        for comb_strat_name in matched_combined_strategies:
            self.parameterInfos[comb_strat_name] = {}
            param_list = param_info[comb_strat_name]
            
            for p in param_list:
                param = ParameterInfo.parseInfo(p)
                if param.strategy_name not in self.parameterInfos[comb_strat_name]:
                    self.parameterInfos[comb_strat_name][param.strategy_name] = []
                self.parameterInfos[comb_strat_name][param.strategy_name].append(param)
    
    def fetch_all_values(self):
        for comb_strat, strategies in self.parameterInfos.items():
            for strategy_name, params in strategies.items():
                for param in params:
                    param.fetch_value()
    
    def returnValues(self):
        res = {}
        for comb_strat, strategies in self.parameterInfos.items():
            res[comb_strat] = {}
            for strategy_name, params in strategies.items():
                res[comb_strat][strategy_name] = {param.name: param.value for param in params}
        return res


PARAMETER_INFO = json.loads(os.environ.get("PARAMETERS", "{}"))


def collect_values(event):
    print("Received event:", event)
    triggered_strategy = event["e"]["action"]["functionName"]

    parameters = Parameters(triggered_strategy)
    parameters.parse_parameters(PARAMETER_INFO)
    parameters.fetch_all_values()

    return parameters.returnValues()


def lambda_handler(event, context):
    values = collect_values(event)
    return {
        'statusCode': 200,
        'body': json.dumps(values)
    }
