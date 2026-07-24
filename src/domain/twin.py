from pydantic import BaseModel
from typing import List, Optional
import json
import os


class InputParameter(BaseModel):
    name: str
    dataType: str
    id: str = ""
    value: Optional[float] = None


class OutputParameter(BaseModel):
    name: str
    dataType: str


class Strategy(BaseModel):
    eventName: str
    inputParameters: List[InputParameter] = []
    outputParameters: List[OutputParameter] = []


class Twin(BaseModel):
    name: str
    region: str
    ssm_registry_prefix: str
    hot_reader_arn: str
    twinmaker_workspace_id: str
    strategies: List[Strategy] = []

    def get_strategy(self, name: str) -> Optional[Strategy]:
        return next((s for s in self.strategies if s.eventName == name), None)


class BrokerConfig(BaseModel):
    broker_url: str
    broker_port: int
    broker_username: str
    broker_password: str
    use_tls: bool = False


class Feedback(BaseModel):
    type: str
    topic: str
    brokerKey: Optional[str] = None
    brokerConfig: Optional[BrokerConfig] = None


class NewStrategy(BaseModel):
    name: str
    pathToCode: str
    feedback: Feedback
    strategies: List[str] = []
    resolved_twins: List[Twin] = []
    resolved_strategies: List[Strategy] = []


class FedTwin(BaseModel):
    name: str
    newStrategies: List[NewStrategy] = []


class FedTwinConfig(BaseModel):
    fedTwins: List[FedTwin] = []


class FederationConfig(BaseModel):
    twins: dict[str, Twin] = {}
    fedTwinConfig: FedTwinConfig = FedTwinConfig()
    broker_configs: dict[str, BrokerConfig] = {}

    @classmethod
    def load(cls, twin_input_paths: List[str], fedtwin_path: str, broker_config_path: Optional[str] = None):
        twins = {}
        for path in twin_input_paths:
            with open(path) as f:
                data = json.load(f)
                if "twins" not in data:
                    data = {"twins": [data]}
                for t in data["twins"]:
                    twin = Twin.model_validate(t)
                    twins[twin.name] = twin

        with open(fedtwin_path) as f:
            fed_config = FedTwinConfig.model_validate(json.load(f))

        fedtwin_dir = os.path.dirname(os.path.abspath(fedtwin_path))
        for fed_twin in fed_config.fedTwins:
            for new_strategy in fed_twin.newStrategies:
                strategy_path = os.path.expanduser(new_strategy.pathToCode)
                if not os.path.isabs(strategy_path):
                    strategy_path = os.path.join(fedtwin_dir, strategy_path)
                new_strategy.pathToCode = os.path.abspath(strategy_path)

        broker_configs = {}
        if broker_config_path:
            with open(broker_config_path) as f:
                data = json.load(f)
                broker_configs = {k: BrokerConfig.model_validate(v) for k, v in data.get("brokers", {}).items()}

        config = cls(twins=twins, fedTwinConfig=fed_config, broker_configs=broker_configs)
        config.resolve()
        return config

    def resolve(self):
        for fed_twin in self.fedTwinConfig.fedTwins:
            for new_strategy in fed_twin.newStrategies:
                for strategy_ref in new_strategy.strategies:
                    twin_name, strategy_name = strategy_ref.split(".")
                    twin = self.twins.get(twin_name)
                    if not twin:
                        raise ValueError(f"Twin '{twin_name}' not found")
                    strategy = twin.get_strategy(strategy_name)
                    if not strategy:
                        raise ValueError(f"Strategy '{strategy_name}' not found in Twin '{twin_name}'")
                    new_strategy.resolved_twins.append(twin)
                    new_strategy.resolved_strategies.append(strategy)

                if new_strategy.feedback.type == "EXTERNAL":
                    key = new_strategy.feedback.brokerKey
                    broker = self.broker_configs.get(key)
                    if not broker:
                        raise ValueError(f"No broker config for key '{key}'")
                    new_strategy.feedback.brokerConfig = broker
