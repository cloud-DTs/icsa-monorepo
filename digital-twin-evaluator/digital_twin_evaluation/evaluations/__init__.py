"""Evaluation implementations and their explicit registration."""

from ..contracts import Evaluation
from .roundtrip import RoundtripEvaluation
from .mqtt import MqttEvaluation
from .mqtt_twinmaker import MqttTwinMakerEvaluation


EVALUATIONS: dict[str, Evaluation] = {
    "roundtrip": RoundtripEvaluation(), "mqtt": MqttEvaluation(), "mqtt-twinmaker": MqttTwinMakerEvaluation(),
}


def get_evaluation(name: str) -> Evaluation:
    try:
        return EVALUATIONS[name]
    except KeyError as error:
        raise ValueError(f"Unknown evaluation '{name}'. Available: {', '.join(EVALUATIONS)}") from error
